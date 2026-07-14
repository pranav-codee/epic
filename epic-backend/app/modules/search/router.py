from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from . import service
from .schemas import TicketSearchOut
from ...database import get_db
from ...dependencies import get_current_user
from ...core.rate_limit import limiter

router = APIRouter()


@router.get("/tickets", response_model=TicketSearchOut)
@limiter.limit("60/minute")
def search_tickets(
    request: Request,
    ticket_number: str | None = None,
    status: str | None = None,
    ticket_type: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    employee_id: str | None = None,
    assignment_group_id: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    total, rows, applied_limit, applied_offset = service.search(
        db, me=me, ticket_number=ticket_number, status=status, ticket_type=ticket_type,
        category=category, priority=priority, employee_id=employee_id,
        assignment_group_id=assignment_group_id, q=q,
        limit=limit, offset=offset,
    )
    return {"total": total, "limit": applied_limit, "offset": applied_offset, "results": rows}