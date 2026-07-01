"""Provider factory."""
from ...config import get_settings
from .providers.base import IdentityProvider
from .providers.mock import MockProvider


def get_provider() -> IdentityProvider:
    s = get_settings()
    if s.AUTH_PROVIDER == "entra":
        from .providers.entra import EntraIdProvider  # lazy: avoid httpx import in mock-only dev
        return EntraIdProvider()
    return MockProvider()
