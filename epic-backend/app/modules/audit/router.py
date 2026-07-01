"""
Audit log retrieval. No write endpoints exist — audit rows are produced only by other modules
via service.record(). This enforces REQ-4.8-8 at the HTTP surface as well.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...dependencies import get_current_user
from ...core.rbac import require_role, Role, has_role
from . import service
from .schemas import AuditEntryOut

router = APIRouter()


@router.get("/tickets/{ticket_id}", response_model=list[AuditEntryOut])
def ticket_history(ticket_id: str, db: Session = Depends(get_db), me=Depends(get_current_user)):
    # Role-scope: employees can only see history of their own ticket.
    from ..tickets.service import get_ticket_or_404
    ticket = get_ticket_or_404(db, ticket_id)
    if not has_role(me, Role.IT_ENGINEER, Role.IT_MANAGER, Role.SYSTEM_ADMIN) and ticket.creator_id != me.id:
        raise HTTPException(403, "Forbidden")
    return service.list_for_ticket(db, ticket_id)


@router.get("", response_model=list[AuditEntryOut])
def search_audit(actor_id: str | None = None, action: str | None = None,
                 db: Session = Depends(get_db),
                 _admin=Depends(require_role(Role.IT_MANAGER, Role.SYSTEM_ADMIN))):
    return service.search(db, actor_id=actor_id, action=action)
