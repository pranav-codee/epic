from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from sqlalchemy.orm import Session
from starlette.responses import Response
from . import service
from ...database import get_db
from ...dependencies import get_current_user
from ...core.rbac import require_role, Role, has_role

router = APIRouter()

_DASHBOARD_ROLES = (Role.IT_MANAGER, Role.SYSTEM_ADMIN, Role.IT_ENGINEER)


@router.get("/overview")
def overview(db: Session = Depends(get_db),
             _=Depends(require_role(*_DASHBOARD_ROLES))):
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


@router.get("/export/excel")
def export_excel(db: Session = Depends(get_db),
                  _=Depends(require_role(*_DASHBOARD_ROLES))):
    content = service.build_excel_export(db)
    filename = f"epic-dashboard-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/pdf")
def export_pdf(db: Session = Depends(get_db),
                _=Depends(require_role(*_DASHBOARD_ROLES))):
    content = service.build_pdf_export(db)
    filename = f"epic-dashboard-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )