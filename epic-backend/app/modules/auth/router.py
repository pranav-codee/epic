"""
Authentication endpoints. Production path = Microsoft Entra ID OIDC; dev fallback = Mock provider.
No local passwords (REQ-4.1-3 / NFR-5.3-1).
"""
import secrets, base64
from fastapi import APIRouter, Depends, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from ...database import get_db
from ...config import get_settings
from ...core.security import issue_session, SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS
from ...dependencies import get_current_user
from ..users import service as users_service
from .service import get_provider

router = APIRouter()

_state_cache: dict[str, bool] = {}  # in-memory CSRF state; fine for single-instance dev


@router.get("/login")
def login():
    """Kicks off the OIDC flow."""
    state = secrets.token_urlsafe(24)
    _state_cache[state] = True
    return RedirectResponse(get_provider().authorize_url(state))


@router.get("/mock-login", include_in_schema=False)
def mock_login_page(state: str):
    """Tiny HTML form for the mock provider (dev only)."""
    if get_settings().AUTH_PROVIDER != "mock":
        raise HTTPException(404, "Not found")
    return HTMLResponse(f"""
    <html><body style="font-family: system-ui; max-width: 420px; margin: 4rem auto;">
      <h2>EPIC — Dev Sign-in (Mock Provider)</h2>
      <p style="color:#a33">⚠ Mock provider. Disabled in production. Real users will sign in via Microsoft Authenticator.</p>
      <form method="get" action="/api/v1/auth/callback">
        <input type="hidden" name="state" value="{state}" />
        <label>Email<br/><input name="email" value="alice.engineer@epl.local" style="width:100%"/></label><br/><br/>
        <button type="submit">Sign in</button>
      </form>
    </body></html>
    """)


@router.get("/callback")
async def callback(state: str, request: Request, db: Session = Depends(get_db),
                   code: str | None = None, email: str | None = None):
    settings = get_settings()
    if state not in _state_cache:
        raise HTTPException(400, "Invalid state")
    _state_cache.pop(state, None)

    # Mock provider: form submits ?email=...  → fabricate `code` from email so the contract stays uniform.
    if settings.AUTH_PROVIDER == "mock" and code is None:
        if not email:
            raise HTTPException(400, "Missing email (mock provider)")
        code = base64.urlsafe_b64encode(email.encode()).decode()

    if not code:
        raise HTTPException(400, "Missing authorization code")

    provider = get_provider()
    try:
        claims = await provider.exchange_code(code)
    except Exception as e:
        raise HTTPException(401, f"Authentication failed: {e}")

    user = users_service.upsert_from_identity(
        db,
        entra_oid=claims.entra_oid,
        email=claims.email,
        display_name=claims.display_name,
        department=claims.department,
    )

    token = issue_session(user.entra_object_id)
    redirect = RedirectResponse(settings.FRONTEND_BASE_URL)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME, value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True, secure=settings.APP_ENV == "prod",
        samesite="lax",
    )
    return redirect


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "department": user.department,
        "roles": user.roles,
    }


# ---- Teams configurable-tab config page (referenced by manifest.json) ----
from .teams_config import router as _teams_cfg_router  # noqa: E402
for r in _teams_cfg_router.routes:
    router.routes.append(r)
