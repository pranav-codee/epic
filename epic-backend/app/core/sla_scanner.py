"""
SLA escalation scanner.

Reuses the existing SLA_HOURS_BY_PRIORITY / sla_status() logic in app/core/sla.py —
this module only adds the missing piece: something that actually *acts* when a
ticket's derived sla_status becomes AT_RISK or BREACHED, instead of that status
just sitting there for a dashboard to read on demand.

Safe to run from multiple app instances at once (see claim_* functions below) —
no distributed lock / message broker needed. Uses the same atomic
UPDATE ... WHERE col IS NULL idiom already used in tickets/service.py's
_next_ticket_number() to avoid a read-modify-write race, applied here to avoid
two instances both sending the same escalation notification.

Drop this file at: app/core/sla_scanner.py
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from .sla import sla_status as compute_sla_status
from ..modules.tickets.models import Ticket
from ..modules.audit import service as audit
from ..modules.audit.models import TicketAuditLog
from ..modules.audit.service import Action
from ..modules.notifications import service as notifier

logger = logging.getLogger(__name__)

# Terminal states — never worth scanning or escalating once a ticket is here.
_TERMINAL_STATES = ("RESOLVED", "CLOSED", "CANCELLED")

# How long a claim can sit with no matching SLA_ESCALATED audit row before we treat it
# as orphaned rather than "another instance is still mid-dispatch." See
# _reclaim_orphaned_claims() below. Generously above any realistic single-request
# latency between _claim()'s commit and _notify()'s audit-row commit two lines later.
_STALE_CLAIM_GRACE_SECONDS = 120


def _claim(db: Session, ticket_id: str, column: str) -> bool:
    """
    Atomically claim the right to send one specific escalation for one specific
    ticket. Returns True only for the caller that actually flipped the column
    from NULL — so if two instances race on the same ticket in the same scan
    tick, exactly one of them proceeds to notifier.dispatch(...).
    """
    result = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, getattr(Ticket, column).is_(None))
        .values(**{column: datetime.utcnow()})
    )
    db.commit()
    return result.rowcount == 1


def _release(db: Session, ticket_id: str, column: str) -> None:
    """
    Compensating action for a claim whose notification never actually went out.
    Resets the column back to NULL so the *next* scan treats this ticket as
    unnotified again, instead of it being permanently (and incorrectly) marked
    "already handled" just because dispatch happened to fail once.

    Deliberately unconditional (no WHERE ... IS NULL guard) — this instance is
    the one that holds the claim, so it's always correct for it to release it.
    """
    db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(**{column: None})
    )
    db.commit()


def _reclaim_orphaned_claims(db: Session) -> int:
    """
    Detect and reset claims that were never followed by a completed _notify() call —
    e.g. because the process was killed (OOM, SIGKILL, container eviction) in the
    narrow window after _claim()'s commit but before _notify() ran at all.

    Why this matters: a claim like that leaves sla_*_notified_at permanently set with
    no notification ever having gone out. scan_and_escalate()'s candidate query only
    looks at tickets where that column IS NULL, so without this pass, an orphaned
    claim is silently invisible to every future scan forever — the ticket just stops
    getting escalated.

    How we tell "orphaned" apart from "legitimately notified" (which *also* leaves the
    column set, forever, by design): _notify() always writes an Action.SLA_ESCALATED
    audit row and commits it *before* attempting dispatch — whether dispatch ultimately
    succeeds or fails (a failed dispatch is released separately via _release(), which
    resets the column back to NULL on its own). So a claim is orphaned if and only if
    the column is set and there's no SLA_ESCALATED audit row for this ticket+event
    created at or after that claim. We compare against the claim timestamp specifically
    (not "any row ever") so a ticket that goes through more than one AT_RISK/BREACHED
    cycle over its lifetime — e.g. after a priority change resets these columns — isn't
    matched against a stale audit row from an earlier, unrelated cycle.

    The grace period avoids a false positive against a claim that's genuinely still
    in-flight on another instance whose audit commit just hasn't landed yet.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=_STALE_CLAIM_GRACE_SECONDS)
    reclaimed = 0

    for column, event in (
        ("sla_at_risk_notified_at", "SLA_AT_RISK"),
        ("sla_breached_notified_at", "SLA_BREACHED"),
    ):
        stale_claims = (
            db.query(Ticket)
            .filter(
                Ticket.status.notin_(_TERMINAL_STATES),
                getattr(Ticket, column).isnot(None),
                getattr(Ticket, column) < cutoff,
            )
            .all()
        )
        for ticket in stale_claims:
            claimed_at = getattr(ticket, column)
            has_matching_audit_row = (
                db.query(TicketAuditLog.id)
                .filter(
                    TicketAuditLog.ticket_id == ticket.id,
                    TicketAuditLog.action == Action.SLA_ESCALATED,
                    TicketAuditLog.new_value == event,
                    TicketAuditLog.created_at >= claimed_at,
                )
                .first()
            )
            if has_matching_audit_row is None:
                logger.warning(
                    f"Reclaiming orphaned SLA claim: ticket_id={ticket.id}, "
                    f"column={column}, claimed_at={claimed_at} — no matching "
                    f"SLA_ESCALATED audit row found; likely a process crash between "
                    f"claim and notify. Resetting so the next scan retries it."
                )
                _release(db, ticket.id, column)
                reclaimed += 1

    return reclaimed


def scan_and_escalate(db: Session) -> dict:
    """
    One pass: reclaim any orphaned claims from a previous crashed run, then look at
    every non-terminal ticket that hasn't already been notified for its current SLA
    state, and escalate the ones that need it.

    Called on a timer (see start_background_loop below). Cheap to call often —
    the WHERE clause only pulls tickets that could still need a notification.
    """
    reclaimed = _reclaim_orphaned_claims(db)
    if reclaimed:
        logger.info(f"SLA scan: reclaimed {reclaimed} orphaned claim(s) before this pass")

    candidates = (
        db.query(Ticket)
        .filter(
            Ticket.status.notin_(_TERMINAL_STATES),
            Ticket.sla_due_at.isnot(None),
        )
        .filter(
            (Ticket.sla_at_risk_notified_at.is_(None))
            | (Ticket.sla_breached_notified_at.is_(None))
        )
        .all()
    )

    at_risk_sent = 0
    breached_sent = 0

    for ticket in candidates:
        status = compute_sla_status(
            priority=ticket.priority,
            created_at=ticket.created_at,
            sla_due_at=ticket.sla_due_at,
            resolved_at=ticket.resolved_at,
            closed_at=ticket.closed_at,
        )

        try:
            if status == "BREACHED" and ticket.sla_breached_notified_at is None:
                if _claim(db, ticket.id, "sla_breached_notified_at"):
                    if _notify(db, ticket, event="SLA_BREACHED", column="sla_breached_notified_at"):
                        breached_sent += 1

            elif status == "AT_RISK" and ticket.sla_at_risk_notified_at is None:
                if _claim(db, ticket.id, "sla_at_risk_notified_at"):
                    if _notify(db, ticket, event="SLA_AT_RISK", column="sla_at_risk_notified_at"):
                        at_risk_sent += 1

        except Exception:
            # One bad ticket shouldn't stop the rest of the scan from running.
            logger.exception(f"SLA escalation failed for ticket_id={ticket.id}")
            db.rollback()
            continue

    logger.info(
        f"SLA scan complete: {len(candidates)} candidates, "
        f"{at_risk_sent} at-risk sent, {breached_sent} breached sent, "
        f"{reclaimed} orphaned claim(s) reclaimed"
    )
    return {
        "candidates": len(candidates),
        "at_risk_sent": at_risk_sent,
        "breached_sent": breached_sent,
        "reclaimed": reclaimed,
    }


def _notify(db: Session, ticket: Ticket, *, event: str, column: str) -> bool:
    """
    Record the audit entry and dispatch the Teams notification for a claimed
    escalation. Returns True if the notification was actually sent.

    FIX: previously, `notifier.dispatch()` could raise (webhook down, network
    blip, etc.) *after* the claim in `_claim()` had already been committed —
    so a failed send still left the ticket permanently marked "notified," and
    it would never be retried. The scanner's outer per-ticket except/rollback
    couldn't undo this, because the claim lives in its own already-committed
    transaction by the time dispatch runs.

    Fix: catch dispatch failures here specifically, and explicitly release the
    claim (reset the column back to NULL) so the ticket is picked up again on
    the next scan tick instead of silently disappearing.
    """
    audit.record(
        db, ticket_id=ticket.id, actor_id=None, action=Action.SLA_ESCALATED,
        field="sla_status", new_value=event,
    )
    db.commit()

    try:
        # recipient_id is metadata on the NotificationRecord, not per-recipient routing —
        # v1 has a single Teams channel, same as every other event in this system.
        notifier.dispatch(
            db, event=event, ticket=ticket, actor_name="EPIC SLA Monitor",
            recipient_id=ticket.assignee_id,
        )
        return True
    except Exception:
        logger.exception(
            f"SLA notification dispatch failed for ticket_id={ticket.id}, event={event}; "
            f"releasing claim on {column} so it is retried next scan"
        )
        _release(db, ticket.id, column)
        return False