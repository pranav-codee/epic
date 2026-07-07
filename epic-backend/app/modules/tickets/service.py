"""
Ticket Management — service layer.

Design rule (NFR-5.4-7 extensibility): every mutation goes through this module, never inlined
in router code. A future AI Orchestrator can call these functions directly to obtain the same
audit + notification behaviour without duplicating logic.
"""
from datetime import datetime, timezone
from sqlalchemy import update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from .models import Ticket, TicketComment, TicketAttachment, TicketCounter, CATEGORIES, PRIORITIES, STATUSES, TICKET_TYPES
from .state_machine import next_state, event_for_target, allowed_target_states_for, RESOLVED, CLOSED, CANCELLED
from ..audit import service as audit
from ..audit.service import Action
from ..notifications import service as notifier
from ..users.models import UserProfile
from ...config import get_settings
from ...core.exceptions import NotFound, Forbidden, DomainError, StorageQuotaExceeded
from ...core.rbac import Role


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
    That makes the increment atomic at the database level on every backend — SQLite included
    — without needing dialect-specific locking, because no Python code ever computes the new
    value from a value it read separately.
    """
    year = datetime.utcnow().year

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


# ---------- Core mutations ----------

def create_ticket(db: Session, *, creator, title: str, description: str, ticket_type: str, category: str, priority: str) -> Ticket:
    if ticket_type not in TICKET_TYPES:
        raise DomainError(f"Invalid ticket_type. Allowed: {TICKET_TYPES}")
    if category not in CATEGORIES:
        raise DomainError(f"Invalid category. Allowed: {CATEGORIES}")
    if priority not in PRIORITIES:
        raise DomainError(f"Invalid priority. Allowed: {PRIORITIES}")

    number = _next_ticket_number(db)
    t = Ticket(
        ticket_number=number,
        creator_id=creator.id,
        ticket_type=ticket_type,
        category=category,
        priority=priority,
        status="OPEN",
        title=title.strip(),
        description=description.strip(),
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
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.TYPE_CHANGE,
                 field="ticket_type", old_value=old, new_value=ticket_type)
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


def change_status(db: Session, *, ticket_id: str, target_status: str, actor) -> Ticket:
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
        ticket.resolved_at = datetime.utcnow()
    if new_state == CLOSED:
        ticket.closed_at = datetime.utcnow()

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
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.PRIORITY_CHANGE,
                 field="priority", old_value=old, new_value=priority)
    db.commit(); db.refresh(ticket)
    notifier.dispatch(db, event="TICKET_UPDATED", ticket=ticket, actor_name=actor.display_name,
                      recipient_id=ticket.creator_id)
    return ticket


def add_comment(db: Session, *, ticket_id: str, text: str, actor) -> TicketComment:
    ticket = get_ticket_or_404(db, ticket_id)
    _ensure_visibility(ticket, actor)
    c = TicketComment(ticket_id=ticket.id, author_id=actor.id, text=text.strip())
    db.add(c); db.flush()
    audit.record(db, ticket_id=ticket.id, actor_id=actor.id, action=Action.COMMENT_ADDED,
                 metadata={"comment_id": c.id, "text_preview": text[:120]})
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