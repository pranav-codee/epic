from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from . import service
from .schemas import TicketSearchOut
from ...database import get_db
from ...dependencies import get_current_user

router = APIRouter()


@router.get("/tickets", response_model=TicketSearchOut)
def search_tickets(
    ticket_number: str | None = None,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    employee_id: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    me=Depends(get_current_user),
):
    total, rows = service.search(db, me=me, ticket_number=ticket_number,
                                 status=status, category=category, priority=priority,
                                 employee_id=employee_id, q=q)
    return {"total": total, "results": rows}
