"""
Mock identity provider — ONLY for local dev when Entra credentials are not yet provisioned.
Selected by setting AUTH_PROVIDER=mock. Never enable in production.

Flow:
  /authorize?state=...&email=alice@epl.local  ->  redirect back with code = base64(email)
"""
import base64, urllib.parse
from .base import IdentityProvider, IdentityClaims
from ....config import get_settings


class MockProvider(IdentityProvider):
    def authorize_url(self, state: str) -> str:
        s = get_settings()
        # In the mock flow the "login page" is just a tiny HTML form served by /auth/mock-login.
        return f"{s.APP_BASE_URL}/api/v1/auth/mock-login?state={urllib.parse.quote(state)}"

    async def exchange_code(self, code: str) -> IdentityClaims:
        try:
            email = base64.urlsafe_b64decode(code.encode()).decode()
        except Exception:
            raise ValueError("Invalid mock code")
        local = email.split("@")[0]
        return IdentityClaims(
            entra_oid=f"mock-{email}",
            email=email,
            display_name=local.replace(".", " ").title(),
            department="Dev",
        )
