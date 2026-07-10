"""
EPIC FastAPI application entrypoint.
Mounts each SRS module under /api/v1/<module> so they remain independently testable (NFR-5.4-4).
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from .core.rate_limit import limiter
from .core.exceptions import DomainError, domain_error_handler
from .database import Base, engine, SessionLocal
from . import models  # noqa: F401  — ensures all models are registered

from .modules.auth.router import router as auth_router
from .modules.users.router import router as users_router
from .modules.tickets.router import router as tickets_router
from .modules.audit.router import router as audit_router
from .modules.notifications.router import router as notifications_router
from .modules.search.router import router as search_router
from .modules.knowledge_base.router import router as kb_router
from .modules.reporting.router import router as reporting_router


def create_app() -> FastAPI:
    settings = get_settings()
    # in create_app(), right after settings = get_settings()
    if settings.APP_ENV == "prod":
       if settings.SESSION_SECRET == "change-me-in-prod":
           raise RuntimeError("SESSION_SECRET must be set to a real secret in production")
       if settings.AUTH_PROVIDER == "mock":
           raise RuntimeError("AUTH_PROVIDER=mock is not allowed when APP_ENV=prod")
    app = FastAPI(title="EPIC v1 — Enterprise Platform for Intelligent IT Collaboration", version="1.0.0")

    # CORS: tight allowlist; the Teams tab loads under teams.microsoft.com and tenant subdomains.
    # NOTE: Starlette's CORSMiddleware does exact-string matching on allow_origins — it does NOT
    # glob-expand "*". Wildcard subdomains must go through allow_origin_regex instead.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_BASE_URL],
        allow_origin_regex=r"^https://([a-zA-Z0-9-]+\.)?teams\.microsoft\.com$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Free bandwidth/latency win: compress responses over 500 bytes (the default minimum_size).
    # No architecture change, no client-side change needed — every modern browser and the
    # Teams webview both send Accept-Encoding: gzip already.
    app.add_middleware(GZipMiddleware, minimum_size=500)

    app.add_exception_handler(DomainError, domain_error_handler)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    api_prefix = "/api/v1"
    app.include_router(auth_router, prefix=f"{api_prefix}/auth", tags=["auth"])
    app.include_router(users_router, prefix=f"{api_prefix}/users", tags=["users"])
    app.include_router(tickets_router, prefix=f"{api_prefix}/tickets", tags=["tickets"])
    app.include_router(audit_router, prefix=f"{api_prefix}/audit", tags=["audit"])
    app.include_router(notifications_router, prefix=f"{api_prefix}/notifications", tags=["notifications"])
    app.include_router(search_router, prefix=f"{api_prefix}/search", tags=["search"])
    app.include_router(kb_router, prefix=f"{api_prefix}/kb", tags=["knowledge-base"])
    app.include_router(reporting_router, prefix=f"{api_prefix}/dashboard", tags=["dashboard"])

    @app.get("/health", tags=["meta"])
    def health():
        # The previous version of this endpoint only proved the FastAPI process was alive —
        # it always returned 200 even if SQL Server was completely unreachable. A monitoring
        # probe or load balancer health check needs to know the difference between "the app
        # is up" and "the app is up but can't talk to its database," since only one of those
        # is something worth paging someone about.
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        status_code = 200 if db_ok else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ok" if db_ok else "degraded",
                    "app": settings.APP_NAME, "env": settings.APP_ENV,
                    "database": "ok" if db_ok else "unreachable"},
        )

    # Dev convenience: auto-create tables if using SQLite. In production, use Alembic only.
    if settings.DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)

    # Periodic SLA at-risk/breach scan. Safe to run on every app instance behind the load
    # balancer — see app/core/sla_scanner.py's atomic-claim logic for why this doesn't
    # produce duplicate notifications.
    from .core.sla_scanner_loop import start_background_loop
    start_background_loop()

    return app


app = create_app()