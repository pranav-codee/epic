"""Provider factory."""
from ...config import get_settings
from .providers.base import IdentityProvider
from .providers.mock import MockProvider


def get_provider() -> IdentityProvider:
    s = get_settings()
    if s.AUTH_PROVIDER == "entra":
        from .providers.entra import EntraIdProvider  # lazy: avoid httpx import in mock-only dev
        return EntraIdProvider()
    if s.AUTH_PROVIDER == "mock":
        return MockProvider()
    # Fail closed (CWE-636): this used to fall through to MockProvider() for *any*
    # value other than "entra" — so a typo'd or blank AUTH_PROVIDER (e.g. "Entra",
    # "prod", "") would silently select the no-auth mock provider instead of refusing
    # to start. main.py's prod guardrail only rejects the exact string "mock", so it
    # would not have caught this either. An unrecognized value should be a startup
    # error, not a silent downgrade to the least secure option.
    raise RuntimeError(
        f"Unknown AUTH_PROVIDER={s.AUTH_PROVIDER!r}. Expected 'entra' or 'mock'."
    )