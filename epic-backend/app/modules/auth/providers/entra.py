"""
Microsoft Entra ID OIDC provider. Uses authorization-code flow.
Requires ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET, ENTRA_REDIRECT_URI.

Microsoft Authenticator MFA enforcement is configured at the Entra tenant Conditional Access policy
level (NFR-5.3-2). The app itself does not implement a parallel MFA flow.
"""
import httpx
from urllib.parse import urlencode
from .base import IdentityProvider, IdentityClaims
from ....config import get_settings


class EntraIdProvider(IdentityProvider):
    def __init__(self):
        s = get_settings()
        self.tenant = s.ENTRA_TENANT_ID
        self.client_id = s.ENTRA_CLIENT_ID
        self.client_secret = s.ENTRA_CLIENT_SECRET
        self.redirect_uri = s.ENTRA_REDIRECT_URI
        self.scopes = s.ENTRA_SCOPES
        if not (self.tenant and self.client_id and self.client_secret):
            raise RuntimeError("Entra provider selected but ENTRA_* env vars not configured.")

    def _auth_base(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0"

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "response_mode": "query",
            "scope": self.scopes,
            "state": state,
        }
        return f"{self._auth_base()}/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str) -> IdentityClaims:
        token_url = f"{self._auth_base()}/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            tr = await client.post(token_url, data=data)
            tr.raise_for_status()
            access_token = tr.json()["access_token"]

            ur = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            ur.raise_for_status()
            me = ur.json()

        return IdentityClaims(
            entra_oid=me["id"],
            email=me.get("mail") or me.get("userPrincipalName"),
            display_name=me.get("displayName") or "Unknown",
            department=me.get("department"),
        )
