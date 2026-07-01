from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from sqlalchemy.orm import Session
from . import service
from ...database import get_db
from ...dependencies import get_current_user
from ...core.rbac import require_role, Role, has_role

router = APIRouter()


@router.get("/overview")
def overview(db: Session = Depends(get_db),
             _=Depends(require_role(Role.IT_MANAGER, Role.SYSTEM_ADMIN, Role.IT_ENGINEER))):
    return service.overview(db)


@router.get("/engineer/me")
def my_workload(db: Session = Depends(get_db),
                me=Depends(require_role(Role.IT_ENGINEER, Role.IT_MANAGER, Role.SYSTEM_ADMIN))):
    return service.engineer_workload(db, me.id)


@router.get("/engineer/{engineer_id}")
def workload(engineer_id: str, db: Session = Depends(get_db),
             _=Depends(require_role(Role.IT_MANAGER, Role.SYSTEM_ADMIN))):
    return service.engineer_workload(db, engineer_id)


@router.get("/reports/tickets")
def report_tickets(group_by: str = "status", from_: str | None = None, to: str | None = None,
                   db: Session = Depends(get_db),
                   _=Depends(require_role(Role.IT_MANAGER, Role.SYSTEM_ADMIN))):
    try:
        from_dt = datetime.fromisoformat(from_) if from_ else None
        to_dt = datetime.fromisoformat(to) if to else None
    except ValueError:
        raise HTTPException(400, "Invalid date format; use ISO-8601")
    try:
        return service.report_group(db, group_by, from_dt, to_dt)
    except ValueError as e:
        raise HTTPException(400, str(e))
