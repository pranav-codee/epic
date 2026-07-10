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

    # Fail fast on an unrecognized AUTH_PROVIDER in any environment, not just prod.
    # get_provider() (modules/auth/service.py) now also fails closed on this, but
    # catching it here means a bad config never even starts accepting traffic,
    # instead of failing on the first request to /login.
    if settings.AUTH_PROVIDER not in ("entra", "mock"):
        raise RuntimeError(
            f"Unknown AUTH_PROVIDER={settings.AUTH_PROVIDER!r}. Expected 'entra' or 'mock'."
        )

    if settings.APP_ENV == "prod":
        if settings.SESSION_SECRET == "change-me-in-prod":
            raise RuntimeError("SESSION_SECRET must be set to a real secret in production")
        if settings.AUTH_PROVIDER == "mock":
            raise RuntimeError("AUTH_PROVIDER=mock is not allowed when APP_ENV=prod")
        if settings.FRONTEND_BASE_URL.startswith(("http://localhost", "http://127.0.0.1")):
            # FRONTEND_BASE_URL is passed straight into CORSMiddleware's allow_origins
            # below, with allow_credentials=True. Leaving it on the dev default in prod
            # means the deployed API would trust cookies/credentials from whatever's
            # running on *someone's* localhost:5173, not the real frontend.
            raise RuntimeError(
                "FRONTEND_BASE_URL is still a localhost dev default; set it to the real "
                "frontend origin before running with APP_ENV=prod."
            )

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

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)

        # HSTS: only meaningful (and only sent) over a connection that's actually HTTPS —
        # sending it over plain HTTP in dev would be a lie the browser can't act on, and
        # in prod every request already terminates TLS at the load balancer/APP_ENV=prod.
        if settings.APP_ENV == "prod":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Stop the browser from MIME-sniffing a response into executing as something
        # other than its declared Content-Type (e.g. an uploaded attachment as HTML/JS).
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Framing: EPIC is deliberately loaded inside an iframe by the Teams tab (see
        # CORS allow_origin_regex above), so a blanket X-Frame-Options: DENY or even
        # SAMEORIGIN would break that. CSP's frame-ancestors is the modern replacement
        # and, unlike X-Frame-Options, supports multiple/wildcard sources — restrict
        # framing to our own frontend origin and Teams' domains only.
        response.headers["Content-Security-Policy"] = (
            f"frame-ancestors 'self' {settings.FRONTEND_BASE_URL} "
            "https://teams.microsoft.com https://*.teams.microsoft.com"
        )

        return response

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
    from .core.sla_scanner_loop import start_background_loop, stop_background_loop as stop_sla_loop
    start_background_loop()

    # Periodic retry sweep for notifications that failed on first send (e.g. a
    # transient Teams webhook outage). Without this, a FAILED/RETRYING record
    # just sits there forever and the recipient never finds out.
    from .core.notification_retry_loop import (
        start_background_loop as start_notification_retry_loop,
        stop_background_loop as stop_notification_retry_loop,
    )
    start_notification_retry_loop()

    @app.on_event("shutdown")
    def _stop_background_loops():
        # FIX: both loops used to be fire-and-forget daemon threads with no shutdown
        # hook anywhere — on a graceful stop (e.g. SIGTERM during a rolling deploy)
        # the process could exit mid-scan/mid-sweep instead of letting each thread
        # finish its current unit of work. Signal both to stop and give them a short,
        # bounded window to exit cleanly; they remain daemon threads regardless, so a
        # slow/blocked iteration still can't hang process shutdown indefinitely.
        stop_sla_loop()
        stop_notification_retry_loop()

    return app


app = create_app()