from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from . import service
from .schemas import NotificationOut
from ...database import get_db
from ...core.rbac import require_role, Role

router = APIRouter()


@router.get("", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db),
                       _admin=Depends(require_role(Role.SYSTEM_ADMIN))):
    """Admin observability: see Teams delivery attempts + failures (NFR-5.4-2)."""
    return service.list_recent(db)
