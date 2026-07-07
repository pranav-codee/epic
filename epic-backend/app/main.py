"""
EPIC FastAPI application entrypoint.
Mounts each SRS module under /api/v1/<module> so they remain independently testable (NFR-5.4-4).
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from .core.rate_limit import limiter
from .core.exceptions import DomainError, domain_error_handler
from .database import Base, engine
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
        return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}

    # Dev convenience: auto-create tables if using SQLite. In production, use Alembic only.
    if settings.DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)

    return app


app = create_app()