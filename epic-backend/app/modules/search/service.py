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


# Fix: previously `limit` had no upper bound and no `offset`, and the router
# never exposed either — callers were silently capped at the first 100 rows
# with no way to page further. total_count is still returned so the frontend
# can compute total pages.
MAX_PAGE_SIZE = 200


def search(db, *, me,
           ticket_number: str | None = None,
           status: str | None = None,
           ticket_type: str | None = None,
           category: str | None = None,
           priority: str | None = None,
           employee_id: str | None = None,
           assignment_group_id: str | None = None,
           q: str | None = None,
           limit: int = 100,
           offset: int = 0):
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
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
    if assignment_group_id:
        # Supports a single id ("grp-1") or a comma-separated list ("grp-1,grp-2") so the
        # frontend's "My Group's Tickets" quick-filter can pass every group the caller
        # belongs to in one request.
        group_ids = [g.strip() for g in assignment_group_id.split(",") if g.strip()]
        if len(group_ids) == 1:
            query = query.filter(Ticket.assignment_group_id == group_ids[0])
        elif group_ids:
            query = query.filter(Ticket.assignment_group_id.in_(group_ids))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Ticket.title.like(like), Ticket.description.like(like)))

    total = query.with_entities(func.count(Ticket.id)).scalar() or 0
    results = query.order_by(Ticket.created_at.desc()).offset(offset).limit(limit).all()
    # Return the clamped values too, not just what was requested, so the caller
    # (and the API response) reflects what was actually applied.
    return total, results, limit, offset