"""
Audit-write API used by every ticket mutation. Treat this as the only legitimate way to
record ticket history. Audit rows are never updated or deleted from the application layer.
"""
import json
from sqlalchemy.orm import Session
from .models import TicketAuditLog
from ..users.models import UserProfile


# Canonical action names — keep stable; reports & dashboards key off these.
class Action:
    CREATE = "CREATE"
    ASSIGN = "ASSIGN"
    STATUS_CHANGE = "STATUS_CHANGE"
    # SPEC §3: ticket-type-specific workflow_status transition (PROGRESSING/ON_HOLD/
    # PEND_3RDPARTY/PEND_USER/APPROVED/RESOLVED or .../IN_APPROVAL/FULFILLED) — distinct from
    # STATUS_CHANGE above, which tracks the pre-existing generic `status` field.
    WORKFLOW_STATUS_CHANGE = "WORKFLOW_STATUS_CHANGE"
    PRIORITY_CHANGE = "PRIORITY_CHANGE"
    TYPE_CHANGE = "TYPE_CHANGE"
    COMMENT_ADDED = "COMMENT_ADDED"
    ATTACHMENT_UPLOADED = "ATTACHMENT_UPLOADED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    # SLA scanner escalations (app.core.sla_scanner) — no human actor, actor_id is None.
    SLA_ESCALATED = "SLA_ESCALATED"

    # --- System / account security events (no associated ticket) ---
    # These close the A09 (Security Logging & Monitoring Failure) gap: previously role
    # grants/revocations, forced logouts, and logins produced no audit trail at all.
    ROLE_GRANT = "ROLE_GRANT"
    ROLE_REVOKE = "ROLE_REVOKE"
    FORCE_LOGOUT = "FORCE_LOGOUT"
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"


def record(db: Session, *, actor_id: str | None, action: str, ticket_id: str | None = None,
           field: str | None = None, old_value=None, new_value=None, metadata: dict | None = None) -> TicketAuditLog:
    entry = TicketAuditLog(
        ticket_id=ticket_id,
        actor_id=actor_id,
        action=action,
        field=field,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(entry)
    db.flush()
    return entry


def _attach_actor_info(db: Session, entries: list[TicketAuditLog]) -> list[TicketAuditLog]:
    """Attach actor_name/actor_email as transient attributes so the API can show 'who' made
    each change without exposing raw actor_id UUIDs to the frontend."""
    actor_ids = {e.actor_id for e in entries if e.actor_id}
    if not actor_ids:
        for e in entries:
            e.actor_name = None
            e.actor_email = None
        return entries

    users = {u.id: u for u in db.query(UserProfile).filter(UserProfile.id.in_(actor_ids)).all()}
    for e in entries:
        u = users.get(e.actor_id)
        e.actor_name = u.display_name if u else ("System" if e.actor_id is None else None)
        e.actor_email = u.email if u else None
    return entries


def list_for_ticket(db: Session, ticket_id: str):
    entries = (db.query(TicketAuditLog)
                 .filter(TicketAuditLog.ticket_id == ticket_id)
                 .order_by(TicketAuditLog.id.asc())
                 .all())
    return _attach_actor_info(db, entries)


def search(db: Session, *, actor_id: str | None = None, action: str | None = None, limit: int = 200):
    q = db.query(TicketAuditLog)
    if actor_id:
        q = q.filter(TicketAuditLog.actor_id == actor_id)
    if action:
        q = q.filter(TicketAuditLog.action == action)
    entries = q.order_by(TicketAuditLog.id.desc()).limit(limit).all()
    return _attach_actor_info(db, entries)