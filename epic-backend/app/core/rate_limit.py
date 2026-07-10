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

    CORRECTNESS NOTE (fixed): X-Forwarded-For is built by each hop *appending* whatever it
    received to the header the client sent it: "<client-supplied>, <what proxy1 actually
    saw>, <what proxy2 actually saw>, ...". That means the LEFTMOST entry is whatever the
    original client put there — fully attacker-controlled — and only entries appended by a
    proxy we ourselves trust are verified. Reading the first (leftmost) entry, as this
    function used to, handed the "fresh fake IP per request" bypass straight back to any
    external client, since nothing here ever inspects it. The fix walks the chain from the
    RIGHT (the hop closest to us, which we already know is a trusted proxy) and returns the
    first entry that ISN'T a known trusted proxy — that's the first hop whose claimed IP
    wasn't independently verified by someone we trust, i.e. the real client.
    """
    direct_ip = get_remote_address(request)
    settings = get_settings()
    trusted = settings.trusted_proxy_ips_set
    if direct_ip not in trusted:
        # Direct connection, or an untrusted/unconfigured intermediary — never trust a header
        # that anyone in that position could set to anything they like.
        return direct_ip

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        # Trusted proxy didn't set the header (misconfigured proxy, or a health check that
        # bypasses it) — fall back to the direct IP rather than erroring the request.
        return direct_ip

    # X-Forwarded-For can be a chain: "client, proxy1, proxy2, ...". Walk it from the right
    # (closest to us) and skip over entries that are themselves trusted proxies — those were
    # each independently appended by a proxy we trust, so we know they're accurate. The first
    # entry we hit that ISN'T a trusted proxy is the first untrusted claim in the chain, i.e.
    # the real client IP. If every entry turns out to be a trusted proxy (misconfiguration —
    # a proxy forwarding to itself, or an incomplete TRUSTED_PROXY_IPS list), fall back to the
    # leftmost entry rather than trusting the direct peer's own claim about itself.
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    for hop in reversed(hops):
        if hop not in trusted:
            return hop
    return hops[0] if hops else direct_ip


limiter = Limiter(key_func=get_real_client_ip)