"""
Role-scoped ticket search. Per BR-3/BR-4:
- EMPLOYEE only sees rows where they're the creator OR the requestor (see the FIX note
  on the base filter below)
- IT_ENGINEER / IT_MANAGER / SYSTEM_ADMIN see all
"""
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload
from ..tickets.models import Ticket
from ..users.models import UserProfile
from ...core.rbac import Role


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
        # FIX: was `Ticket.creator_id == me.id` only, so an employee's own search never
        # found a ticket someone else filed on their behalf (Ticket.requestor_id) — same
        # underlying gap as tickets/service.py's _ensure_visibility()/list_for_user().
        query = query.filter(or_(Ticket.creator_id == me.id, Ticket.requestor_id == me.id))

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
        # FIX: was `Ticket.creator_id == employee_id` only. An IT engineer/manager/admin
        # looking up "this employee's tickets" — e.g. while on a call with them — needs
        # tickets raised *for* that employee to show up too, not just ones they personally
        # submitted through the portal themselves.
        query = query.filter(or_(Ticket.creator_id == employee_id, Ticket.requestor_id == employee_id))
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
    return total, results, limit, offset