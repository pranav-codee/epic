"""
Shared rate limiter instance. Lives in its own module (rather than app/main.py) so that
router modules can import it without creating a circular import with main.py, which itself
imports all the routers.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from ..config import get_settings


def get_real_client_ip(request: Request) -> str:
    """
    Rate-limit key function.

    In production this app sits behind IIS/nginx, so request.client.host (what
    slowapi.util.get_remote_address returns by default) is always the PROXY's IP, never the
    real employee's — meaning all ~2,300 employees would silently share ONE rate-limit bucket
    instead of each getting their own. That's not hypothetical: running a concurrency test
    against this app locally reproduced exactly this, since every simulated "different user"
    shared one machine's IP and immediately tripped limits meant to apply per-person.

    Fix: only trust the X-Forwarded-For header when the request's direct TCP peer is a
    configured, known proxy (TRUSTED_PROXY_IPS). Never trust it unconditionally — if we did,
    any external client could set X-Forwarded-For to a fresh fake IP on every request and
    dodge rate limiting entirely, which would be worse than the bug we're fixing.
    """
    direct_ip = get_remote_address(request)
    settings = get_settings()
    if direct_ip not in settings.trusted_proxy_ips_set:
        # Direct connection, or an untrusted/unconfigured intermediary — never trust a header
        # that anyone in that position could set to anything they like.
        return direct_ip

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        # Trusted proxy didn't set the header (misconfigured proxy, or a health check that
        # bypasses it) — fall back to the direct IP rather than erroring the request.
        return direct_ip

    # X-Forwarded-For can be a chain: "client, proxy1, proxy2, ...". Each proxy in the chain
    # appends the IP it received the request from, so the FIRST entry is the original client —
    # everything after it was appended by proxies we may or may not also trust.
    return forwarded.split(",")[0].strip()


limiter = Limiter(key_func=get_real_client_ip)