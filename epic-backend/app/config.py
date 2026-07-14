"""
Central configuration. Driven entirely by environment variables (NFR-5.3-5: no secrets in source).
See .env.example for required variables.
"""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "EPIC"
    APP_ENV: str = Field(default="dev")          # dev | staging | prod
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_BASE_URL: str = "http://localhost:8000"
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    SESSION_SECRET: str = "change-me-in-prod"    # used to sign session cookie

    # --- Database ---
    # TODO (production): point to on-prem MS SQL Server, e.g.
    #   mssql+pyodbc://USER:PASS@HOST:1433/EPIC?driver=ODBC+Driver+18+for+SQL+Server
    # For local dev we fall back to SQLite (E1 user decision, 30-Jun-2026).
    DATABASE_URL: str = "sqlite:///./epic_dev.db"

    # --- Auth (Microsoft Entra ID / Microsoft Authenticator) ---
    # AUTH_PROVIDER = "entra" in prod, "mock" only for local dev when Entra creds are not yet provisioned.
    AUTH_PROVIDER: str = "mock"
    ENTRA_TENANT_ID: str = ""
    ENTRA_CLIENT_ID: str = ""
    ENTRA_CLIENT_SECRET: str = ""
    ENTRA_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/callback"
    ENTRA_SCOPES: str = "openid profile email User.Read"

    # --- Notifications (Microsoft Teams) ---
    # One Incoming Webhook URL per category-channel is fine; v1 uses a single channel.
    # TODO: replace with real EPL Teams webhook before pilot (TBD-3 in SRS Appendix C).
    TEAMS_WEBHOOK_URL: str = ""
    TEAMS_NOTIFICATIONS_ENABLED: bool = True

    # --- Attachments ---
    ATTACHMENT_DIR: str = "./storage/attachments"
    ATTACHMENT_MAX_BYTES: int = 25 * 1024 * 1024   # 25 MB (default A2)
    # Resource Exhaustion (CWE-770) fix: previously only a single-file size cap existed, so a
    # user could still upload unlimited attachments (or unlimited total bytes) to a single
    # ticket, or across all their tickets, and exhaust disk space. Add explicit caps.
    ATTACHMENT_MAX_PER_TICKET: int = 20
    ATTACHMENT_MAX_TOTAL_BYTES_PER_TICKET: int = 100 * 1024 * 1024    # 100 MB per ticket
    ATTACHMENT_MAX_TOTAL_BYTES_PER_USER: int = 500 * 1024 * 1024      # 500 MB per user (all tickets)
    # ALLOWLIST, not a denylist: an attachment's extension AND sniffed content must both match
    # one of these entries. Denylists are trivially bypassed (rename, unlisted extension, etc).
    ATTACHMENT_ALLOWED_EXTENSIONS: str = ".png,.jpg,.jpeg,.gif,.pdf,.txt,.log,.csv,.docx,.xlsx,.pptx,.zip"
    ATTACHMENT_ALLOWED_MIME_TYPES: str = (
        "image/png,image/jpeg,image/gif,application/pdf,text/plain,text/csv,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
        "application/zip,application/x-zip-compressed"
    )

    # --- SLA escalation scanner (app.core.sla_scanner / sla_scanner_loop) ---
    SLA_SCAN_ENABLED: bool = True
    SLA_SCAN_INTERVAL_SECONDS: int = 300   # 5 minutes; tune once real ticket volume is known

    # --- Daily open-ticket-by-group snapshot (app.core.daily_snapshot_loop) ---
    # Backs Production View A's "Yesterday's Backlog" column (reporting/service.py's
    # daily_ops_summary()), which needs each Assignment Group's open-ticket count as of
    # yesterday — a value a live query can no longer answer once today's tickets have
    # already mutated the open-ticket set. take_daily_snapshot() is idempotent per
    # snapshot_date (deletes-then-reinserts that date's rows), so a 24h interval that
    # happens to fire more than once on a given day is harmless.
    DAILY_SNAPSHOT_ENABLED: bool = True
    DAILY_SNAPSHOT_INTERVAL_SECONDS: int = 86400   # 24 hours

    # --- Misc ---
    BOOTSTRAP_ADMIN_EMAILS: str = ""   # comma-separated emails granted SYSTEM_ADMIN on first login

    # --- Reverse proxy / rate limiting ---
    # In production this app sits behind IIS/nginx, so every request's direct TCP peer is the
    # proxy, not the real employee. Without this, slowapi's rate limiter would key on the
    # proxy's IP for every single request — meaning all ~2,300 employees would share ONE
    # rate-limit bucket instead of getting their own. List the proxy's IP(s) here so
    # core/rate_limit.py knows when it's safe to trust the X-Forwarded-For header instead of
    # the raw connection IP. Leave as 127.0.0.1 for local dev (the loopback the dev server
    # itself runs on); set to the real reverse-proxy host's IP(s) in prod, comma-separated if
    # there's more than one (e.g. an HA pair).
    TRUSTED_PROXY_IPS: str = "127.0.0.1"

    # --- Monitoring-tool ingestion endpoint (SPEC §6) ---
    # Static service-token bearer credential for POST /tickets/ingest/monitoring. That
    # endpoint is machine-to-machine traffic (a monitoring tool, not a human), so it can't
    # authenticate via the session-cookie flow every other endpoint uses — see
    # dependencies.require_monitoring_ingest_token. Left empty by default so the endpoint
    # fails closed (401 on every request, per SPEC §9) until an operator explicitly
    # provisions a token via env.
    MONITORING_INGEST_TOKEN: str = ""

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.ATTACHMENT_ALLOWED_EXTENSIONS.split(",") if e.strip()}

    @property
    def allowed_mime_types(self) -> set[str]:
        return {m.strip().lower() for m in self.ATTACHMENT_ALLOWED_MIME_TYPES.split(",") if m.strip()}

    @property
    def bootstrap_admin_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.BOOTSTRAP_ADMIN_EMAILS.split(",") if e.strip()}

    @property
    def trusted_proxy_ips_set(self) -> set[str]:
        return {ip.strip() for ip in self.TRUSTED_PROXY_IPS.split(",") if ip.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()