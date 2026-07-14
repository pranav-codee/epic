"""
Ticket Management — service layer.

Design rule (NFR-5.4-7 extensibility): every mutation goes through this module, never inlined
in router code. A future AI Orchestrator can call these functions directly to obtain the same
audit + notification behaviour without duplicating logic.
"""
from sqlalchemy import update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from .models import Ticket, TicketComment, TicketAttachment, TicketCounter, CATEGORIES, PRIORITIES, STATUSES, TICKET_TYPES, CHANNELS
from .state_machine import next_state, event_for_target, allowed_target_states_for, RESOLVED, CLOSED, CANCELLED
from . import workflow as wf
from ..audit import service as audit
from ..audit.service import Action
from ..catalogue.models import Location
from ..notifications import service as notifier
from ..users.models import UserProfile
from ...config import get_settings
from ...core.exceptions import NotFound, Forbidden, DomainError, StorageQuotaExceeded
from ...core.rbac import Role
# SPEC §4 Part 2 (this session): ticket creation/priority-change/first-response/
# resolution now go through the business-hours engine below instead of the old 24/7
# compute_due_at() path — see /PROGRESS.md Session 4 and core/sla.py's module docstring.
from ...core.sla import (
    compute_business_hours_sla_due_dates, resolve_location_timezone, DEFAULT_SLA_TIMEZONE,
    business_hours_sla_result, effective_due_at,
)
from ...core.time import utcnow


# ---------- Helpers ----------

def _next_ticket_number(db: Session) -> str:
    """
    Allocate the next ticket number for the current year.

    Previous version read `last_number` into Python, incremented it there, then wrote it
    back — a classic read-modify-write race. It used `with_for_update()` to guard against
    that, but skipped the lock on SQLite (SQLite doesn't support row-level locks the same
    way), which left dev/test environments exposed to duplicate ticket numbers under
    concurrent requests.

    Fix: do the "+1" inside the UPDATE statement itself (`last_number = last_number + 1`).
    That makes the increment atomic at the database level on every backend — SQLite
    included — without needing dialect-specific locking, because no Python code ever computes
    the new value from a value it read separately.
    """
    year = utcnow().year

    if db.query(TicketCounter).filter(TicketCounter.year == year).one_or_none() is None:
        db.add(TicketCounter(year=year, last_number=0))
        try:
            db.flush()
        except IntegrityError:
            # Another concurrent request created this year's row first — fine, continue.
            db.rollback()

    db.execute(
        update(TicketCounter)
        .where(TicketCounter.year == year)
        .values(last_number=TicketCounter.last_number + 1)
    )
    db.flush()
    new_number = db.query(TicketCounter.last_number).filter(TicketCounter.year == year).scalar()
    return f"EPIC-{year}-{new_number:06d}"


def get_ticket_or_404(db: Session, ticket_id: str) -> Ticket:
    t = db.query(Ticket).filter(Ticket.id == ticket_id).one_or_none()
    if not t:
        raise NotFound(f"Ticket {ticket_id} not found")
    return t


def _ensure_visibility(ticket: Ticket, user) -> None:
    """Employees see only their own tickets (BR-3). Engineers/managers/admins see all (BR-4)."""
    roles = set(user.roles or [])
    if roles & {Role.IT_ENGINEER.value, Role.IT_MANAGER.value, Role.SYSTEM_ADMIN.value}:
        return
    if ticket.creator_id != user.id:
        raise Forbidden("You can only view your own tickets")


def _is_engineer(user) -> bool:
    return bool(set(user.roles or []) & {Role.IT_ENGINEER.value, Role.IT_MANAGER.value, Role.SYSTEM_ADMIN.value})


# ---------- SPEC §3: Resolution SLA pause-clock bookkeeping ----------
# See workflow.py module docstring and models.py's sla_paused_at/sla_paused_total_seconds
# comments: this session tracks *when* the ticket was paused and *how long* it has spent
# paused in total, so a later §4 business-hours SLA engine can subtract that time without
# replaying the audit log. It intentionally does not compute due-date shifts itself.

def _start_sla_pause(ticket: Ticket) -> None:
    if ticket.sla_paused_at is None:
        ticket.sla_paused_at = utcnow()


def _end_sla_pause(ticket: Ticket) -> None:
    if ticket.sla_paused_at is not None:
        elapsed = (utcnow() - ticket.sla_paused_at).total_seconds()
        ticket.sla_paused_total_seconds = (ticket.sla_paused_total_seconds or 0) + max(0, int(elapsed))
        ticket.sla_paused_at = None


# ---------- SPEC §4 Part 2: business-hours SLA wiring ----------
# See /PROGRESS.md Session 4 for the full write-up of the decisions baked into the
# helpers below (the "first response" definition, the breached_reason enforcement
# mechanism, and how SPEC §3's pause bookkeeping is consumed here).

def _resolve_sla_timezone(db: Session, location_id: str | None) -> str:
    """
    SPEC §4: business hours are measured in the ticket's location's local timezone.
    Falls back to core.sla.DEFAULT_SLA_TIMEZONE (matching Location's own HO/Asia-Kolkata
    default) for tickets that have no location at all — SPEC §1 already left
    Ticket.location_id nullable at the DB level (not every existing user has a
    home_location yet), and SPEC §4 must still produce a due date either way rather than
    leaving response_due_at/resolution_due_at NULL.
    """
    if location_id:
        loc = db.query(Location).filter(Location.id == location_id).one_or_none()
        if loc is not None:
            try:
                return resolve_location_timezone(loc)
            except ValueError:
                pass
    return DEFAULT_SLA_TIMEZONE


def _apply_sla_evaluation(db: Session, ticket: Ticket, *, field: str, result: str,
                          breached_reason: str | None, actor) -> None:
    """
    Sets `ticket.response_sla_status` or `ticket.resolution_sla_status` to a freshly
    computed MET/BREACHED result, and is the single choke point both the first-response
    and resolution evaluation paths funnel through — so a third caller added later can't
    accidentally bypass the SPEC §1 rule this enforces:

        "breached_reason (free text) — required server-side when either SLA status is
        Breached."

    Enforced here as app-layer validation (raises DomainError, not a DB constraint, per
    this session's explicit instructions) rather than at the DB layer, since the DB has
    no way to express "required only when a sibling column has a specific value."
    Accepts an already-set `ticket.breached_reason` from an earlier breach on the *other*
    clock (both SLA statuses share the one breached_reason column on Ticket — see
    models.py) so a ticket that's already BREACHED on its Response clock doesn't force a
    second, redundant reason when Resolution also breaches later; a fresh
    `breached_reason` argument always overrides/updates it if one is supplied.
    """
    old = getattr(ticket, field)
    if result == "BREACHED":
        reason = (breached_reason or ticket.breached_reason or "").strip()
        if not reason:
            raise DomainError(
                f"breached_reason is required when {field} is set to BREACHED. "
                "Resubmit this request including a breached_reason.")
        ticket.breached_reason = reason
    setattr(ticket, field, result)
    audit.record(
        db, ticket_id=ticket.id, actor_id=actor.id if actor else None,
        action=Action.RESPONSE_SLA_EVALUATED if field == "response_sla_status" else Action.RESOLUTION_SLA_EVALUATED,
        field=field, old_value=old, new_value=result)


def _record_first_response(db: Session, *, ticket: Ticket, actor, at, breached_reason: str | None) -> None:
    """
    SPEC §4 Part 2's "on first response" bullet. "First response" is defined (this
    session's explicit choice, documented in /PROGRESS.md Session 4) as: the first
    comment added by IT support staff (Engineer/Manager/Admin — the same
    `_is_engineer()` check used everywhere else in this file) on a ticket that hasn't
    had one yet. Called from `add_comment()` below.
    """
    ticket.first_response_at = at
    due = effective_due_at(ticket.response_due_at, ticket.sla_paused_total_seconds)
    result = business_hours_sla_result(due_at=due, actual_at=at)
    if result is None:
        # No response_due_at to evaluate against (e.g. a ticket that predates this
        # session's columns) — first_response_at is still recorded above, just no
        # MET/BREACHED verdict to render.
        return
    _apply_sla_evaluation(db, ticket, field="response_sla_status", result=result,
                          breached_reason=breached_reason, actor=actor)


def _record_resolution(db: Session, *, ticket: Ticket, actor, breached_reason: str | None) -> None:
    """
    SPEC §4 Part 2's "on resolution" bullet. Must be called *after* `ticket.resolved_at`
    is set and after any in-flight SLA pause has been ended (`_end_sla_pause`), so
    `ticket.sla_paused_total_seconds` reflects the ticket's full paused time before this
    function reads it.

    SPEC §3 pause-clock note ("Resolution SLA clock pauses during
    PEND_USER/PEND_3RDPARTY"): the base `status`/`STATUSES` field this session was told
    to check has no PEND_USER/PEND_3RDPARTY entries (STATUSES in tickets/models.py is
    OPEN/ASSIGNED/IN_PROGRESS/PENDING_USER/RESOLVED/CLOSED/CANCELLED — no PEND_3RDPARTY,
    and PENDING_USER isn't the same value as PEND_USER). Those two states DO already
    exist in this codebase, though — as `workflow_status` values (SPEC §3, Session 2),
    complete with the `sla_paused_at`/`sla_paused_total_seconds` bookkeeping Session 2
    built specifically so this moment could consume it. Rather than re-reading that as
    "the statuses don't exist, skip the pause math," this session wires resolution
    evaluation against `sla_paused_total_seconds` (via `effective_due_at()`) regardless
    of which of the two mutation paths (`change_status` or `change_workflow_status`)
    actually resolved the ticket — both already call `_end_sla_pause()` before this
    function runs. See /PROGRESS.md Session 4 for the full reasoning on this deviation
    from a literal reading of the STATUSES check.
    """
    due = effective_due_at(ticket.resolution_due_at, ticket.sla_paused_total_seconds)
    result = business_hours_sla_result(due_at=due, actual_at=ticket.resolved_at)
    if result is None:
        return
    _apply_sla_evaluation(db, ticket, field="resolution_sla_status", result=result,
                          breached_reason=breached_reason, actor=actor)


# ---------- Core mutations ----------

def create_ticket(db: Session, *, creator, title: str, description: str, ticket_type: str, category: str,
                  priority: str, requestor_id: str | None = None, location_id: str | None = None,
                  channel: str = "SELF_SERVICE", assignment_group_id: str | None = None,
                  device_name: str | None = None, device_ip_address: str | None = None,
                  device_site_name: str | None = None) -> Ticket:
    if ticket_type not in TICKET_TYPES:
        raise DomainError(f"Invalid ticket_type. Allowed: {TICKET_TYPES}")
    if category not in CATEGORIES:
        raise DomainError(f"Invalid category. Allowed: {CATEGORIES}")
    if priority not in PRIORITIES:
        raise DomainError(f"Invalid priority. Allowed: {PRIORITIES}")
    if channel not in CHANNELS:
        raise DomainError(f"Invalid channel. Allowed: {CHANNELS}")

    number = _next_ticket_number(db)
    now = utcnow()

    # SPEC §1: location is auto-filled from the creator's home_location at creation, but the
    # caller (e.g. an agent logging on someone's behalf) may override it explicitly.
    effective_location_id = location_id or getattr(creator, "home_location_id", None)

    # SPEC §4 Part 2: Response + Resolution SLA due timestamps, computed via the Part 1
    # business-hours engine in the ticket's location's local timezone — replaces the old
    # 24/7 compute_due_at() path entirely for new tickets.
    sla_timezone = _resolve_sla_timezone(db, effective_location_id)
    sla_due_dates = compute_business_hours_sla_due_dates(
        ticket_type=ticket_type, priority=priority, start=now, timezone_name=sla_timezone)

    t = Ticket(
        ticket_number=number,
        creator_id=creator.id,
        # SPEC §1: requestor vs created_by — defaults to the creator when nobody else is named.
        requestor_id=requestor_id or creator.id,
        ticket_type=ticket_type,
        category=category,
        priority=priority,
        status="OPEN",
        # SPEC §3: INCIDENT/SERVICE_REQUEST tickets start their type-specific workflow at
        # PROGRESSING; PROBLEM/CHANGE_REQUEST have no §3-defined workflow (stays NULL).
        workflow_status=wf.initial_workflow_status(ticket_type),
        title=title.strip(),
        description=description.strip(),
        created_at=now,
        response_due_at=sla_due_dates["response_due_at"],
        resolution_due_at=sla_due_dates["resolution_due_at"],
        # Legacy alias kept in sync with resolution_due_at — see models.py comment.
        sla_due_at=sla_due_dates["resolution_due_at"],
        location_id=effective_location_id,
        channel=channel,
        assignment_group_id=assignment_group_id,
        device_name=device_name if channel == "MONITORING_TOOL" else None,
        device_ip_address=device_ip_address if channel == "MONITORING_TOOL" else None,
        device_site_name=device_site_name if channel == "MONITORING_TOOL" else None,
    )
    db.add(t); db.flush()

    audit.record(db, ticket_id=t.id, actor_id=creator.id, action=Action.CREATE,
                 metadata={"ticket_number": number, "ticket_type": ticket_type, "category": category, "priority": priority})
    db.commit(); db.refresh(t)

    notifier.dispatch(db, event="TICKET_CREATED", ticket=t, actor_name=creator.display_name,
                      recipient_id=creator.id)
    return t


def reclassify_ticket(db: Session, *, ticket_id: str, ticket_type: str, actor) -> Ticket:
    """Change a ticket's type — e.g. promoting a recurring INCIDENT to a PROBLEM once root-cause
    investigation is warranted. Only IT staff may reclassify."""
    if not _is_engineer(actor):
        raise Forbidden("Only IT Engineers may reclassify tickets")
    if ticket_type not in TICKET_TYPES:
        raise DomainError(f"Invalid ticket_type. Allowed: {TICKET_TYPES}")
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.status in (CLOSED, CANCELLED):
        raise DomainError(f"Cannot reclassify a ticket in terminal state {ticket.status}")
    old = ticket.ticket_type
    if old == ticket_type:
        return ticket
    ticket.ticket_type = ticket_type
    # SPEC §3: workflow_status is scoped to ticket_type (INCIDENT vs SERVICE_REQUEST have
    # different — and differently-named — terminal/approval states, so an old value from the
    # previous type would be meaningless, or worse, silently valid-looking under the new
    # type's transition graph). Reclassifying always resets to that type's initial state (or
    # NULL if the new type has no §3 workflow) rather than trying to map states across the two
    # graphs — there's no spec-defined equivalence between e.g. INCIDENT's APPROVED and
    # SERVICE_REQUEST's IN_APPROVAL to justify carrying progress over. Any accumulated SLA
    # pause time is preserved either way since that's tracked on the ticket, not the state.
    old_workflow_status = ticket.workflow_status
    if wf.is_pause_state(old_workflow_status) and ticket.sla_paused_at is not None:
        _end_sla_pause(ticket)
    ticket.workflow_status = wf.initial_workflow_status(ticket_type)
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.TYPE_CHANGE,
                 field="ticket_type", old_value=old, new_value=ticket_type)
    if old_workflow_status != ticket.workflow_status:
        audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.WORKFLOW_STATUS_CHANGE,
                     field="workflow_status", old_value=old_workflow_status, new_value=ticket.workflow_status,
                     metadata={"reason": "ticket_type_changed"})
    db.commit(); db.refresh(ticket)
    notifier.dispatch(db, event="TICKET_UPDATED", ticket=ticket, actor_name=actor.display_name,
                      recipient_id=ticket.creator_id)
    return ticket


def assign_ticket(db: Session, *, ticket_id: str, assignee_id: str, actor) -> Ticket:
    if not _is_engineer(actor):
        raise Forbidden("Only IT Engineers may assign tickets")
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.status in (CLOSED, CANCELLED):
        raise DomainError(f"Cannot assign a ticket in terminal state {ticket.status}")
    assignee = db.query(UserProfile).filter(UserProfile.id == assignee_id).one_or_none()
    if not assignee:
        raise NotFound("Assignee user not found")

    # Broken Access Control fix: the UI dropdown previously listed every user (via GET /users)
    # with no role filter, and the API never re-checked that the chosen assignee actually is
    # support staff. Enforce it server-side — never trust the client to have filtered the list.
    from ..users.models import UserRoleAssignment
    assignee_roles = {r.role for r in db.query(UserRoleAssignment)
                       .filter(UserRoleAssignment.user_id == assignee.id).all()}
    support_roles = {Role.IT_ENGINEER.value, Role.IT_MANAGER.value, Role.SYSTEM_ADMIN.value}
    if not assignee_roles & support_roles:
        raise DomainError("Tickets can only be assigned to IT support staff "
                          "(IT Engineer, IT Manager, or System Admin)")

    # State transition: OPEN -> ASSIGNED if currently OPEN; otherwise just record a re-assignment.
    old_assignee_id = ticket.assignee_id
    ticket.assignee_id = assignee.id
    if ticket.status == "OPEN":
        ticket.status = next_state(ticket.status, "assign")
        audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.STATUS_CHANGE,
                     field="status", old_value="OPEN", new_value="ASSIGNED")
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.ASSIGN,
                 field="assignee_id", old_value=old_assignee_id, new_value=assignee.id)
    db.commit(); db.refresh(ticket)

    notifier.dispatch(db, event="TICKET_ASSIGNED", ticket=ticket, actor_name=actor.display_name,
                      recipient_id=ticket.creator_id)
    return ticket


def change_status(db: Session, *, ticket_id: str, target_status: str, actor,
                  breached_reason: str | None = None) -> Ticket:
    if not _is_engineer(actor):
        raise Forbidden("Only IT Engineers may change ticket status")
    if target_status not in STATUSES:
        raise DomainError(f"Invalid target status. Allowed: {STATUSES}")
    ticket = get_ticket_or_404(db, ticket_id)
    event = event_for_target(ticket.status, target_status)
    if event is None:
        raise DomainError(f"No transition from {ticket.status} to {target_status}")
    new_state = next_state(ticket.status, event)
    old = ticket.status
    ticket.status = new_state
    if new_state == RESOLVED:
        ticket.resolved_at = utcnow()
    if new_state == CLOSED:
        ticket.closed_at = utcnow()
    if new_state in (RESOLVED, CLOSED, CANCELLED) and ticket.sla_paused_at is not None:
        # A ticket can reach a terminal legacy status while workflow_status is still sitting
        # in a pause state (e.g. an engineer resolves via this endpoint rather than the §3
        # workflow-status one) — stop the pause clock either way so it never runs forever.
        # Must happen BEFORE _record_resolution below so sla_paused_total_seconds already
        # reflects this final pause segment.
        _end_sla_pause(ticket)

    if new_state == RESOLVED:
        # SPEC §4 Part 2: evaluate resolution_sla_status now that resolved_at is set.
        # Can raise DomainError (breached_reason required) — caught below so nothing
        # from this request (including the status change itself) is left half-applied.
        try:
            _record_resolution(db, ticket=ticket, actor=actor, breached_reason=breached_reason)
        except DomainError:
            db.rollback()
            raise

    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.STATUS_CHANGE,
                 field="status", old_value=old, new_value=new_state)
    if new_state == CLOSED:
        audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.CLOSED)
    if new_state == CANCELLED:
        audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.CANCELLED)
    db.commit(); db.refresh(ticket)

    event_map = {
        "RESOLVED": "TICKET_RESOLVED",
        "CLOSED":   "TICKET_CLOSED",
        "CANCELLED": "TICKET_CANCELLED",
    }
    notif_event = event_map.get(new_state, "TICKET_UPDATED")
    notifier.dispatch(db, event=notif_event, ticket=ticket, actor_name=actor.display_name,
                      recipient_id=ticket.creator_id)
    return ticket


def change_workflow_status(db: Session, *, ticket_id: str, target_workflow_status: str, actor,
                           breached_reason: str | None = None) -> Ticket:
    """SPEC §3: move a ticket through its ticket-type-specific workflow
    (PROGRESSING/ON_HOLD/PEND_3RDPARTY/PEND_USER/APPROVED/RESOLVED for Incidents;
    PROGRESSING/ON_HOLD/PEND_3RDPARTY/PEND_USER/IN_APPROVAL/FULFILLED for Service Requests).

    Same permission model as change_status (only IT staff drive workflow — SPEC §9's
    fail-closed requirement applies here exactly as it does to the existing endpoint this
    mirrors). Also starts/stops the SLA pause clock (see _start_sla_pause/_end_sla_pause)
    and mirrors terminal states into `resolved_at` so existing SLA-status/reporting code that
    already reads `resolved_at` keeps working without needing to know about workflow_status.
    """
    if not _is_engineer(actor):
        raise Forbidden("Only IT Engineers may change ticket workflow status")
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.status in (CLOSED, CANCELLED):
        raise DomainError(f"Cannot change workflow status of a ticket in terminal state {ticket.status}")

    valid_states = wf.workflow_statuses_for(ticket.ticket_type)
    if not valid_states:
        raise DomainError(
            f"SPEC §3 defines no workflow for ticket_type={ticket.ticket_type}; "
            f"workflow_status can only be changed on INCIDENT or SERVICE_REQUEST tickets."
        )
    if target_workflow_status not in valid_states:
        raise DomainError(
            f"Invalid workflow_status for {ticket.ticket_type}. Allowed: {valid_states}")

    current = ticket.workflow_status
    if current is None:
        # Defensive: shouldn't happen for a WORKFLOW_ENABLED ticket_type post-creation, but
        # covers rows that predate this column (see models.py comment) — treat as "not yet
        # started" and let it initialize into the workflow from PROGRESSING going forward,
        # fail closed rather than guessing a transition.
        raise DomainError(
            "This ticket has no workflow_status yet; it predates SPEC §3 and cannot be "
            "transitioned automatically. Contact a System Admin.")

    event = wf.event_for_workflow_target(ticket.ticket_type, current, target_workflow_status)
    if event is None:
        raise DomainError(f"No workflow transition from {current} to {target_workflow_status} "
                          f"for a {ticket.ticket_type} ticket")

    new_state = wf.next_workflow_state(ticket.ticket_type, current, event)

    # Pause-clock: stop the clock when leaving a pause state, start it when entering one.
    was_paused = wf.is_pause_state(current)
    will_be_paused = wf.is_pause_state(new_state)
    if was_paused and not will_be_paused:
        _end_sla_pause(ticket)
    elif will_be_paused and not was_paused:
        _start_sla_pause(ticket)
    # (pause -> pause, e.g. PEND_USER -> PEND_3RDPARTY, isn't reachable via the transition
    # graphs above — both require passing back through PROGRESSING — so no case for it here.)

    ticket.workflow_status = new_state
    if wf.is_terminal_workflow_state(new_state) and ticket.resolved_at is None:
        # Mirror into the existing resolved_at column so reporting/SLA-status code that
        # already reads it (see Ticket.sla_status, core/sla.py) reflects the workflow
        # reaching RESOLVED/FULFILLED, without needing a §3-aware rewrite this session.
        ticket.resolved_at = utcnow()
        # SPEC §4 Part 2: evaluate resolution_sla_status now that resolved_at is set.
        # was_paused/will_be_paused above already ended any in-flight pause (via
        # _end_sla_pause) before this point, so sla_paused_total_seconds is final.
        try:
            _record_resolution(db, ticket=ticket, actor=actor, breached_reason=breached_reason)
        except DomainError:
            db.rollback()
            raise

    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.WORKFLOW_STATUS_CHANGE,
                 field="workflow_status", old_value=current, new_value=new_state)
    db.commit(); db.refresh(ticket)

    notif_event = "TICKET_RESOLVED" if wf.is_terminal_workflow_state(new_state) else "TICKET_UPDATED"
    notifier.dispatch(db, event=notif_event, ticket=ticket, actor_name=actor.display_name,
                      recipient_id=ticket.creator_id)
    return ticket


def cancel_ticket(db: Session, *, ticket_id: str, actor) -> Ticket:
    """Employees may cancel their own pre-resolved tickets; engineers may cancel any.

    Functional-defect fix: this used to delegate to `change_status(...)`, but that
    function unconditionally requires `_is_engineer(actor)` — so an employee could
    never reach CANCELLED for their own ticket even though this function's own
    permission check just approved exactly that. The two checks contradicted each
    other and made employee self-cancel unreachable. Perform the transition directly
    here instead, using the permission check already done above.
    """
    ticket = get_ticket_or_404(db, ticket_id)
    if not _is_engineer(actor) and ticket.creator_id != actor.id:
        raise Forbidden("You can only cancel your own tickets")

    event = event_for_target(ticket.status, "CANCELLED")
    if event is None:
        raise DomainError(f"No transition from {ticket.status} to CANCELLED")
    old = ticket.status
    ticket.status = next_state(ticket.status, event)
    if ticket.sla_paused_at is not None:
        _end_sla_pause(ticket)

    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.STATUS_CHANGE,
                 field="status", old_value=old, new_value=ticket.status)
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.CANCELLED)
    db.commit(); db.refresh(ticket)

    notifier.dispatch(db, event="TICKET_CANCELLED", ticket=ticket, actor_name=actor.display_name,
                      recipient_id=ticket.creator_id)
    return ticket


def change_priority(db: Session, *, ticket_id: str, priority: str, actor) -> Ticket:
    if not _is_engineer(actor):
        raise Forbidden("Only IT Engineers may change priority")
    if priority not in PRIORITIES:
        raise DomainError(f"Invalid priority. Allowed: {PRIORITIES}")
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.status in (CLOSED, CANCELLED):
        raise DomainError(f"Cannot change priority of a ticket in terminal state {ticket.status}")
    old = ticket.priority
    if old == priority:
        return ticket
    ticket.priority = priority
    # Re-baseline the SLA clock from the moment of re-prioritization — a ticket bumped to
    # CRITICAL should get a fresh CRITICAL-length window rather than inheriting a due date
    # computed under the old priority's (usually longer) target. SPEC §4 Part 2 (this
    # session): recomputed via the business-hours engine, same as create_ticket, rather
    # than the old 24/7 compute_due_at() — included in this session's scope alongside
    # creation because leaving change_priority on the old engine while creation moved to
    # the new one would silently desynchronize sla_due_at from response_due_at/
    # resolution_due_at the moment anyone re-prioritized a ticket (see /PROGRESS.md
    # Session 4).
    sla_timezone = _resolve_sla_timezone(db, ticket.location_id)
    sla_due_dates = compute_business_hours_sla_due_dates(
        ticket_type=ticket.ticket_type, priority=priority, start=utcnow(), timezone_name=sla_timezone)
    ticket.response_due_at = sla_due_dates["response_due_at"]
    ticket.resolution_due_at = sla_due_dates["resolution_due_at"]
    ticket.sla_due_at = sla_due_dates["resolution_due_at"]
    # FIX: this reset was previously missing, even though models.py's column comment already
    # claimed it happened. Without it, a ticket already notified AT_RISK/BREACHED under its
    # *old* priority's SLA window kept those notified-at flags set after re-prioritization —
    # so app.core.sla_scanner would treat it as "already handled" and silently skip notifying
    # for its new (often much tighter) window. Clearing both (and now the Response clock's
    # own pair of columns — SPEC §4 Part 2) gives a re-prioritized ticket a fresh
    # notification cycle, matching the fresh due dates it just got.
    ticket.sla_at_risk_notified_at = None
    ticket.sla_breached_notified_at = None
    ticket.response_sla_at_risk_notified_at = None
    ticket.response_sla_breached_notified_at = None
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.PRIORITY_CHANGE,
                 field="priority", old_value=old, new_value=priority)
    db.commit(); db.refresh(ticket)
    notifier.dispatch(db, event="TICKET_UPDATED", ticket=ticket, actor_name=actor.display_name,
                      recipient_id=ticket.creator_id)
    return ticket


def add_comment(db: Session, *, ticket_id: str, text: str, actor,
                breached_reason: str | None = None) -> TicketComment:
    ticket = get_ticket_or_404(db, ticket_id)
    _ensure_visibility(ticket, actor)
    c = TicketComment(ticket_id=ticket.id, author_id=actor.id, text=text.strip())
    db.add(c); db.flush()
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.COMMENT_ADDED,
                 metadata={"comment_id": c.id, "text_preview": text[:120]})

    # SPEC §4 Part 2: "first response" — see _record_first_response's docstring and
    # /PROGRESS.md Session 4 for the definition this session settled on (first
    # support-staff comment). Only fires once per ticket (guarded by
    # ticket.first_response_at is None). Can raise DomainError (breached_reason
    # required) — caught below so nothing from this request, including the comment
    # itself, is left half-applied.
    if _is_engineer(actor) and ticket.first_response_at is None:
        try:
            _record_first_response(db, ticket=ticket, actor=actor, at=utcnow(),
                                   breached_reason=breached_reason)
        except DomainError:
            db.rollback()
            raise

    db.commit(); db.refresh(c)

    # Notify on new comment (D2 user decision, 30-Jun-2026): yes, comments trigger update notification.
    notifier.dispatch(db, event="TICKET_UPDATED", ticket=ticket, actor_name=actor.display_name,
                      recipient_id=ticket.creator_id)
    return c


def add_attachment(db: Session, *, ticket_id: str, file_name: str, content_type: str | None,
                   data: bytes, actor) -> TicketAttachment:
    ticket = get_ticket_or_404(db, ticket_id)
    _ensure_visibility(ticket, actor)

    # Product decision (see cancel_ticket/change_priority terminal-state guards): once a
    # ticket is CLOSED or CANCELLED it's frozen for further file uploads. Comments remain
    # allowed on terminal tickets (people may want to leave a closing note), but attachments
    # do not — there's no more workflow left for anyone to act on them.
    if ticket.status in (CLOSED, CANCELLED):
        raise DomainError(f"Cannot upload attachments to a ticket in terminal state {ticket.status}")

    s = get_settings()
    # Size is already enforced while streaming in the router (before this much of the file
    # is even buffered), but we re-check here too since this function can be called directly.
    if len(data) > s.ATTACHMENT_MAX_BYTES:
        raise DomainError(f"Attachment exceeds {s.ATTACHMENT_MAX_BYTES} bytes")

    # Resource Exhaustion (CWE-770) fix: a single-file size cap alone doesn't stop someone
    # from uploading unlimited files. Cap the number of attachments and total bytes per
    # ticket, and total bytes per user across all their tickets.
    existing_count = (db.query(func.count(TicketAttachment.id))
                       .filter(TicketAttachment.ticket_id == ticket.id).scalar() or 0)
    if existing_count >= s.ATTACHMENT_MAX_PER_TICKET:
        raise StorageQuotaExceeded(
            f"This ticket already has the maximum of {s.ATTACHMENT_MAX_PER_TICKET} attachments")

    existing_ticket_bytes = (db.query(func.coalesce(func.sum(TicketAttachment.size_bytes), 0))
                              .filter(TicketAttachment.ticket_id == ticket.id).scalar() or 0)
    if existing_ticket_bytes + len(data) > s.ATTACHMENT_MAX_TOTAL_BYTES_PER_TICKET:
        raise StorageQuotaExceeded(
            f"This ticket has reached its {s.ATTACHMENT_MAX_TOTAL_BYTES_PER_TICKET}-byte "
            "attachment storage limit")

    existing_user_bytes = (db.query(func.coalesce(func.sum(TicketAttachment.size_bytes), 0))
                            .filter(TicketAttachment.uploaded_by == actor.id).scalar() or 0)
    if existing_user_bytes + len(data) > s.ATTACHMENT_MAX_TOTAL_BYTES_PER_USER:
        raise StorageQuotaExceeded(
            f"You have reached your {s.ATTACHMENT_MAX_TOTAL_BYTES_PER_USER}-byte total "
            "attachment storage limit across all tickets")

    from .attachment_validation import validate_attachment
    try:
        validate_attachment(file_name, content_type, data, s.allowed_extensions, s.allowed_mime_types)
    except ValueError as e:
        raise DomainError(str(e))

    from .storage import get_storage
    uri = get_storage().save(ticket.id, file_name, data)
    att = TicketAttachment(
        ticket_id=ticket.id, uploaded_by=actor.id,
        file_name=file_name, content_type=content_type,
        size_bytes=len(data), storage_uri=uri,
    )
    db.add(att); db.flush()
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.ATTACHMENT_UPLOADED,
                 metadata={"attachment_id": att.id, "file_name": file_name, "size_bytes": len(data)})
    db.commit(); db.refresh(att)
    # NOTE: per D2 user decision (30-Jun-2026), attachment uploads do NOT trigger a Teams notification.
    return att


# ---------- Reads ----------

def list_for_user(db: Session, user, *, limit: int = 200):
    q = db.query(Ticket).options(joinedload(Ticket.creator), joinedload(Ticket.assignee))
    if not _is_engineer(user):
        q = q.filter(Ticket.creator_id == user.id)
    return q.order_by(Ticket.created_at.desc()).limit(limit).all()


def fetch_detail(db: Session, ticket_id: str, user):
    t = (db.query(Ticket)
         .options(joinedload(Ticket.creator), joinedload(Ticket.assignee),
                  joinedload(Ticket.comments).joinedload(TicketComment.author),
                  joinedload(Ticket.attachments))
         .filter(Ticket.id == ticket_id).one_or_none())
    if not t:
        raise NotFound("Ticket not found")
    _ensure_visibility(t, user)
    return t