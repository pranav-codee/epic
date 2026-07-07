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
    q: str | None = None,
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    total, rows = service.search(db, me=me, ticket_number=ticket_number,
                                 status=status, ticket_type=ticket_type, category=category, priority=priority,
                                 employee_id=employee_id, q=q)
    return {"total": total, "results": rows}