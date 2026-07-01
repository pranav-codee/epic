"""
Audit-write API used by every ticket mutation. Treat this as the only legitimate way to
record ticket history. Audit rows are never updated or deleted from the application layer.
"""
import json
from sqlalchemy.orm import Session
from .models import TicketAuditLog


# Canonical action names — keep stable; reports & dashboards key off these.
class Action:
    CREATE = "CREATE"
    ASSIGN = "ASSIGN"
    STATUS_CHANGE = "STATUS_CHANGE"
    PRIORITY_CHANGE = "PRIORITY_CHANGE"
    COMMENT_ADDED = "COMMENT_ADDED"
    ATTACHMENT_UPLOADED = "ATTACHMENT_UPLOADED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


def record(db: Session, *, ticket_id: str, actor_id: str | None, action: str,
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


def list_for_ticket(db: Session, ticket_id: str):
    return (db.query(TicketAuditLog)
              .filter(TicketAuditLog.ticket_id == ticket_id)
              .order_by(TicketAuditLog.id.asc())
              .all())


def search(db: Session, *, actor_id: str | None = None, action: str | None = None, limit: int = 200):
    q = db.query(TicketAuditLog)
    if actor_id:
        q = q.filter(TicketAuditLog.actor_id == actor_id)
    if action:
        q = q.filter(TicketAuditLog.action == action)
    return q.order_by(TicketAuditLog.id.desc()).limit(limit).all()
