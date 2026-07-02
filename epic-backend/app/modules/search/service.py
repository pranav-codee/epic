"""
Role-scoped ticket search. Per BR-3/BR-4:
- EMPLOYEE only sees rows where creator_id == self.id
- IT_ENGINEER / IT_MANAGER / SYSTEM_ADMIN see all
"""
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload
from ..tickets.models import Ticket
from ..users.models import UserProfile
from ...core.rbac import Role


def search(db, *, me,
           ticket_number: str | None = None,
           status: str | None = None,
           ticket_type: str | None = None,
           category: str | None = None,
           priority: str | None = None,
           employee_id: str | None = None,
           q: str | None = None,
           limit: int = 100):
    is_engineer = bool(set(me.roles or []) & {Role.IT_ENGINEER.value, Role.IT_MANAGER.value, Role.SYSTEM_ADMIN.value})

    query = db.query(Ticket).options(joinedload(Ticket.creator), joinedload(Ticket.assignee))
    if not is_engineer:
        query = query.filter(Ticket.creator_id == me.id)

    if ticket_number:
        query = query.filter(Ticket.ticket_number.ilike(f"%{ticket_number}%") if hasattr(Ticket.ticket_number, "ilike") else Ticket.ticket_number.like(f"%{ticket_number}%"))
    if status:
        query = query.filter(Ticket.status == status.upper())
    if ticket_type:
        query = query.filter(Ticket.ticket_type == ticket_type.upper())
    if category:
        query = query.filter(Ticket.category == category.upper())
    if priority:
        query = query.filter(Ticket.priority == priority.upper())
    if employee_id and is_engineer:
        query = query.filter(Ticket.creator_id == employee_id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Ticket.title.like(like), Ticket.description.like(like)))

    total = query.with_entities(func.count(Ticket.id)).scalar() or 0
    results = query.order_by(Ticket.created_at.desc()).limit(limit).all()
    return total, results