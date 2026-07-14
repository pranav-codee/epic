from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime
from sqlalchemy.orm import Session
from starlette.responses import Response
from . import service
from ...database import get_db
from ...dependencies import get_current_user
from ...core.rbac import require_role, Role, has_role
from ...core.rate_limit import limiter
from ...core.time import utcnow

router = APIRouter()

_DASHBOARD_ROLES = (Role.IT_MANAGER, Role.SYSTEM_ADMIN, Role.IT_ENGINEER)


@router.get("/overview")
@limiter.limit("30/minute")
def overview(request: Request, db: Session = Depends(get_db),
             _=Depends(require_role(*_DASHBOARD_ROLES))):
    return service.overview(db)


@router.get("/sla-adherence")
@limiter.limit("30/minute")
def sla_adherence(request: Request, db: Session = Depends(get_db),
                  _=Depends(require_role(*_DASHBOARD_ROLES))):
    """SPEC §4: rolling per-priority SLA adherence (achieved% vs target%), split by
    response/resolution clock. Same role gate as /overview, since this is the same
    dashboard's data, just a dedicated aggregation rather than a slice of overview()."""
    return service.sla_adherence_by_priority(db)


@router.get("/group-status-crosstab")
@limiter.limit("30/minute")
def group_status_crosstab(request: Request, ticket_type: str = "INCIDENT", db: Session = Depends(get_db),
                          _=Depends(require_role(*_DASHBOARD_ROLES))):
    """Production View D: open tickets cross-tabbed by Assignment Group x workflow_status,
    computed separately for INCIDENT vs SERVICE_REQUEST. Same role gate as /overview."""
    try:
        return service.group_by_status_crosstab(db, ticket_type.upper().strip())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/engineer/me")
@limiter.limit("30/minute")
def my_workload(request: Request, db: Session = Depends(get_db),
                me=Depends(require_role(Role.IT_ENGINEER, Role.IT_MANAGER, Role.SYSTEM_ADMIN))):
    return service.engineer_workload(db, me.id)


@router.get("/engineer/{engineer_id}")
@limiter.limit("30/minute")
def workload(engineer_id: str, request: Request, db: Session = Depends(get_db),
             _=Depends(require_role(Role.IT_MANAGER, Role.SYSTEM_ADMIN))):
    return service.engineer_workload(db, engineer_id)


@router.get("/reports/tickets")
@limiter.limit("20/minute")
def report_tickets(request: Request, group_by: str = "status", from_: str | None = None, to: str | None = None,
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


# Export endpoints build a full workbook/PDF from scratch on every call (openpyxl /
# reportlab, plus several DB aggregation queries) — the most expensive requests this
# router serves. They previously had no rate limit at all, unlike every mutating
# ticket endpoint elsewhere in the app; a single authenticated account looping this
# could burn CPU/DB load with no server-side throttle. 10/minute is generous for
# legitimate use (nobody re-exports the same dashboard multiple times a second) while
# capping the worst case.
@router.get("/export/excel")
@limiter.limit("10/minute")
def export_excel(request: Request, db: Session = Depends(get_db),
                  _=Depends(require_role(*_DASHBOARD_ROLES))):
    content = service.build_excel_export(db)
    filename = f"epic-dashboard-{utcnow().strftime('%Y%m%d-%H%M')}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/pdf")
@limiter.limit("10/minute")
def export_pdf(request: Request, db: Session = Depends(get_db),
                _=Depends(require_role(*_DASHBOARD_ROLES))):
    content = service.build_pdf_export(db)
    filename = f"epic-dashboard-{utcnow().strftime('%Y%m%d-%H%M')}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )