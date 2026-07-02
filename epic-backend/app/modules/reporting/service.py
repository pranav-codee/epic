"""Aggregation queries for dashboards and management reporting."""
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..tickets.models import Ticket


def overview(db: Session):
    by_status = dict(db.query(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status).all())
    by_ticket_type = dict(db.query(Ticket.ticket_type, func.count(Ticket.id)).group_by(Ticket.ticket_type).all())
    by_category = dict(db.query(Ticket.category, func.count(Ticket.id)).group_by(Ticket.category).all())
    by_priority = dict(db.query(Ticket.priority, func.count(Ticket.id)).group_by(Ticket.priority).all())
    total = db.query(func.count(Ticket.id)).scalar() or 0
    open_states = ("OPEN", "ASSIGNED", "IN_PROGRESS", "PENDING_USER")
    open_total = db.query(func.count(Ticket.id)).filter(Ticket.status.in_(open_states)).scalar() or 0
    return {
        "total_tickets": total,
        "open_tickets": open_total,
        "by_status": by_status,
        "by_ticket_type": by_ticket_type,
        "by_category": by_category,
        "by_priority": by_priority,
    }


def engineer_workload(db: Session, engineer_id: str):
    rows = (db.query(Ticket.status, func.count(Ticket.id))
              .filter(Ticket.assignee_id == engineer_id)
              .group_by(Ticket.status).all())
    return {
        "engineer_id": engineer_id,
        "by_status": dict(rows),
        "active": sum(c for s, c in rows if s in ("ASSIGNED", "IN_PROGRESS", "PENDING_USER")),
    }


def report_group(db: Session, group_by: str, from_dt=None, to_dt=None):
    col_map = {"status": Ticket.status, "ticket_type": Ticket.ticket_type, "category": Ticket.category, "priority": Ticket.priority}
    col = col_map.get(group_by)
    if col is None:
        raise ValueError(f"group_by must be one of {list(col_map)}")
    q = db.query(col, func.count(Ticket.id)).group_by(col)
    if from_dt:
        q = q.filter(Ticket.created_at >= from_dt)
    if to_dt:
        q = q.filter(Ticket.created_at <= to_dt)
    return [{"key": k, "count": v} for k, v in q.all()]