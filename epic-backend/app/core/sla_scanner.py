"""
SLA escalation scanner.

SPEC §4 Part 2 (this session — see /PROGRESS.md Session 4): now scans the Response and
Resolution clocks INDEPENDENTLY, business-hours-aware, via
`app.core.sla.business_hours_live_status()` — replacing the old single wall-clock
`sla_status()` check that only ever looked at one clock (effectively the Resolution
one, since `sla_due_at` was always the resolution-style deadline). Everything else
about this module's design (atomic claim/release, orphaned-claim reclamation, one
notification per state per clock) is unchanged from before this session.

Safe to run from multiple app instances at once (see claim_* functions below) —
no distributed lock / message broker needed. Uses the same atomic
UPDATE ... WHERE col IS NULL idiom already used in tickets/service.py's
_next_ticket_number() to avoid a read-modify-write race, applied here to avoid
two instances both sending the same escalation notification.

Drop this file at: app/core/sla_scanner.py
"""
import logging
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload

from .sla import (
    business_hours_live_status, get_business_hours_sla_targets, resolve_location_timezone,
    DEFAULT_SLA_TIMEZONE,
)
from .time import utcnow
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

# SPEC §4 Part 2: the two clocks this scanner tracks independently, and everything
# needed to drive each one generically through the same code path below.
#
# The Resolution clock reuses the pre-existing sla_at_risk_notified_at/
# sla_breached_notified_at columns (its only meaning before this session — "the
# ticket's overall due-date scan" — *is* the Resolution clock now that Response is
# split out; see tickets/models.py's SPEC §4 Part 2 comment for why no rename/migration
# was needed). The Response clock is genuinely new — it never had independent
# monitoring before — so it gets its own pair of columns
# (response_sla_at_risk_notified_at / response_sla_breached_notified_at).
#
# `audit_at_risk_value`/`audit_breached_value` are distinct per clock (rather than both
# clocks writing the same "SLA_AT_RISK"/"SLA_BREACHED" new_value) so
# _reclaim_orphaned_claims() can tell which clock's claim a given audit row actually
# reconciles — otherwise a Resolution-clock BREACHED audit row could incorrectly look
# like it also satisfies an orphaned Response-clock BREACHED claim on the same ticket.
# `at_risk_event`/`breached_event` stay the generic "SLA_AT_RISK"/"SLA_BREACHED" strings
# because that's all notifications/templates.py's title_map currently defines — adding
# clock-specific Teams-card wording is out of this session's scope (that file wasn't
# touched).
_CLOCKS = (
    {
        "name": "response",
        "due_field": "response_due_at",
        "minutes_key": "response_minutes",
        "already_fired_field": "first_response_at",
        "at_risk_col": "response_sla_at_risk_notified_at",
        "breached_col": "response_sla_breached_notified_at",
        "at_risk_event": "SLA_AT_RISK",
        "breached_event": "SLA_BREACHED",
        "audit_at_risk_value": "RESPONSE_SLA_AT_RISK",
        "audit_breached_value": "RESPONSE_SLA_BREACHED",
    },
    {
        "name": "resolution",
        "due_field": "resolution_due_at",
        "minutes_key": "resolution_minutes",
        "already_fired_field": "resolved_at",
        "at_risk_col": "sla_at_risk_notified_at",
        "breached_col": "sla_breached_notified_at",
        "at_risk_event": "SLA_AT_RISK",
        "breached_event": "SLA_BREACHED",
        "audit_at_risk_value": "RESOLUTION_SLA_AT_RISK",
        "audit_breached_value": "RESOLUTION_SLA_BREACHED",
    },
)


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
        .values(**{column: utcnow()})
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

    Why this matters: a claim like that leaves a *_notified_at column permanently set
    with no notification ever having gone out. scan_and_escalate()'s candidate query
    only looks at tickets where that column IS NULL, so without this pass, an orphaned
    claim is silently invisible to every future scan forever — the ticket just stops
    getting escalated on that clock.

    How we tell "orphaned" apart from "legitimately notified" (which *also* leaves the
    column set, forever, by design): _notify() always writes an Action.SLA_ESCALATED
    audit row (with a clock-specific new_value — see _CLOCKS above) and commits it
    *before* attempting dispatch — whether dispatch ultimately succeeds or fails (a
    failed dispatch is released separately via _release(), which resets the column back
    to NULL on its own). So a claim is orphaned if and only if the column is set and
    there's no matching SLA_ESCALATED audit row for this ticket+clock+state created at
    or after that claim. We compare against the claim timestamp specifically (not "any
    row ever") so a ticket that goes through more than one AT_RISK/BREACHED cycle over
    its lifetime — e.g. after a priority change resets these columns — isn't matched
    against a stale audit row from an earlier, unrelated cycle.

    The grace period avoids a false positive against a claim that's genuinely still
    in-flight on another instance whose audit commit just hasn't landed yet.
    """
    cutoff = utcnow() - timedelta(seconds=_STALE_CLAIM_GRACE_SECONDS)
    reclaimed = 0

    columns = []
    for clock in _CLOCKS:
        columns.append((clock["at_risk_col"], clock["audit_at_risk_value"]))
        columns.append((clock["breached_col"], clock["audit_breached_value"]))

    for column, audit_value in columns:
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
                    TicketAuditLog.new_value == audit_value,
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


def _resolve_ticket_timezone(ticket: Ticket) -> str:
    """SPEC §4: business hours are measured in the ticket's location's local timezone;
    falls back to core.sla.DEFAULT_SLA_TIMEZONE for tickets with no resolvable
    location, matching tickets/service.py's _resolve_sla_timezone at creation time."""
    if ticket.location is not None:
        try:
            return resolve_location_timezone(ticket.location)
        except ValueError:
            pass
    return DEFAULT_SLA_TIMEZONE


def scan_and_escalate(db: Session) -> dict:
    """
    One pass: reclaim any orphaned claims from a previous crashed run, then look at
    every non-terminal ticket that hasn't already been notified for its current SLA
    state on EITHER clock, and escalate the ones that need it — evaluating the
    Response and Resolution clocks independently (SPEC §4: "Independent Response +
    Resolution clocks"), each in business hours via
    `app.core.sla.business_hours_live_status()`.

    A clock stops being scanned once it has "fired" (first_response_at set for
    Response, resolved_at set for Resolution) — at that point
    tickets/service.py has already evaluated a final MET/BREACHED verdict for it
    directly (SPEC §4 Part 2's "on first response"/"on resolution" bullets), and this
    scanner's job (warn before/at the moment a still-open deadline is missed) no longer
    applies to that clock.

    Called on a timer (see start_background_loop below). Cheap to call often —
    the WHERE clause only pulls tickets that could still need a notification on at
    least one clock.
    """
    reclaimed = _reclaim_orphaned_claims(db)
    if reclaimed:
        logger.info(f"SLA scan: reclaimed {reclaimed} orphaned claim(s) before this pass")

    candidates = (
        db.query(Ticket)
        .options(joinedload(Ticket.location))
        .filter(
            Ticket.status.notin_(_TERMINAL_STATES),
            (Ticket.response_due_at.isnot(None)) | (Ticket.resolution_due_at.isnot(None)),
        )
        .filter(
            (Ticket.response_sla_at_risk_notified_at.is_(None))
            | (Ticket.response_sla_breached_notified_at.is_(None))
            | (Ticket.sla_at_risk_notified_at.is_(None))
            | (Ticket.sla_breached_notified_at.is_(None))
        )
        .all()
    )

    at_risk_sent = 0
    breached_sent = 0
    now = utcnow()

    for ticket in candidates:
        try:
            timezone_name = _resolve_ticket_timezone(ticket)

            for clock in _CLOCKS:
                if getattr(ticket, clock["already_fired_field"]) is not None:
                    # This clock has already fired — tickets/service.py already recorded
                    # its final MET/BREACHED verdict; nothing left for this scanner to
                    # warn about on this clock.
                    continue
                due_at = getattr(ticket, clock["due_field"])
                if due_at is None:
                    continue
                if (getattr(ticket, clock["at_risk_col"]) is not None
                        and getattr(ticket, clock["breached_col"]) is not None):
                    continue  # already notified for both states on this clock

                try:
                    targets = get_business_hours_sla_targets(ticket.ticket_type, ticket.priority)
                except ValueError:
                    logger.warning(
                        f"SLA scan: unresolvable {clock['name']} target for "
                        f"ticket_id={ticket.id} (ticket_type={ticket.ticket_type!r}, "
                        f"priority={ticket.priority!r}); skipping this clock this pass."
                    )
                    continue
                target_minutes = targets[clock["minutes_key"]]

                status = business_hours_live_status(
                    due_at=due_at, created_at=ticket.created_at, timezone_name=timezone_name,
                    target_minutes=target_minutes, now=now,
                    paused_seconds=ticket.sla_paused_total_seconds,
                )

                if status == "BREACHED" and getattr(ticket, clock["breached_col"]) is None:
                    if _claim(db, ticket.id, clock["breached_col"]):
                        if _notify(db, ticket, event=clock["breached_event"], column=clock["breached_col"],
                                  audit_value=clock["audit_breached_value"]):
                            breached_sent += 1

                elif status == "AT_RISK" and getattr(ticket, clock["at_risk_col"]) is None:
                    if _claim(db, ticket.id, clock["at_risk_col"]):
                        if _notify(db, ticket, event=clock["at_risk_event"], column=clock["at_risk_col"],
                                  audit_value=clock["audit_at_risk_value"]):
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


def _notify(db: Session, ticket: Ticket, *, event: str, column: str, audit_value: str) -> bool:
    """
    Record the audit entry and dispatch the Teams notification for a claimed
    escalation. Returns True if the notification was actually sent.

    `audit_value` (e.g. "RESPONSE_SLA_BREACHED") is the clock-specific marker written
    to the audit row's new_value — see _CLOCKS above and _reclaim_orphaned_claims()'s
    docstring for why this needs to be distinct per clock, not just per AT_RISK/BREACHED
    state. `event` (e.g. "SLA_BREACHED") is the separate, clock-agnostic string passed
    to the notification templates, unchanged from before this session.

    FIX (pre-existing, unchanged this session): previously, `notifier.dispatch()` could
    raise (webhook down, network blip, etc.) *after* the claim in `_claim()` had already
    been committed — so a failed send still left the ticket permanently marked
    "notified," and it would never be retried. The scanner's outer per-ticket
    except/rollback couldn't undo this, because the claim lives in its own
    already-committed transaction by the time dispatch runs.

    Fix: catch dispatch failures here specifically, and explicitly release the
    claim (reset the column back to NULL) so the ticket is picked up again on
    the next scan tick instead of silently disappearing.
    """
    audit.record(
        db, ticket_id=ticket.id, actor_id=None, action=Action.SLA_ESCALATED,
        field="sla_status", new_value=audit_value,
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