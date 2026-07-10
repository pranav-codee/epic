"""
Authentication endpoints. Production path = Microsoft Entra ID OIDC; dev fallback = Mock provider.
No local passwords (REQ-4.1-3 / NFR-5.3-1).
"""
import secrets, base64
from fastapi import APIRouter, Depends, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from ...core.rate_limit import limiter
from ...database import get_db
from ...config import get_settings
from ...core.security import (
    issue_session, SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS,
    issue_oauth_state, read_oauth_state, OAUTH_STATE_MAX_AGE_SECONDS,
)
from ...dependencies import get_current_user
from ..users import service as users_service
from ..audit import service as audit
from ..audit.service import Action
from .service import get_provider

router = APIRouter()

# Name of the short-lived cookie that binds an in-flight OAuth `state` value to the
# browser that started the login — see the CSRF note on login()/callback() below.
OAUTH_STATE_COOKIE_NAME = "epic_oauth_state"


@router.get("/login")
@limiter.limit("20/minute")
def login(request: Request):
    """Kicks off the OIDC flow. State is a signed, self-expiring token — no server-side
    storage needed, so this works across multiple app instances behind a load balancer.

    CSRF fix: the signed state token alone only proves it was validly issued by *this
    server at some point* — it doesn't prove it was issued to *this browser*. Without
    binding it to the browser that started the flow, anyone can call /login themselves
    (it's unauthenticated), capture their own valid state+code pair from the resulting
    /callback URL, and send that exact link to a victim. The victim's browser would
    complete the exchange and end up logged in as the attacker (login CSRF) — nothing
    about SameSite=Lax stops this, since setting a cookie in a response isn't gated by
    the incoming request's SameSite policy. Fix: stash the state in a short-lived,
    httponly cookie set here, and require /callback to see that same value again.
    """
    settings = get_settings()
    state = issue_oauth_state(secrets.token_urlsafe(16))
    redirect = RedirectResponse(get_provider().authorize_url(state))
    redirect.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME, value=state,
        max_age=OAUTH_STATE_MAX_AGE_SECONDS,
        httponly=True, secure=settings.APP_ENV == "prod",
        samesite="lax",
    )
    return redirect


@router.get("/mock-login", include_in_schema=False)
@limiter.limit("20/minute")
def mock_login_page(request: Request, state: str):
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
@limiter.limit("20/minute")
async def callback(state: str, request: Request, db: Session = Depends(get_db),
                   code: str | None = None, email: str | None = None):
    settings = get_settings()

    # CSRF fix: require the state presented here to match the one issued to *this*
    # browser at /login (see the comment there). A validly-signed-but-unbound state is
    # not enough — otherwise an attacker's own state+code pair, sent to a victim as a
    # plain link, would silently authenticate the victim as the attacker.
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(400, "Invalid or expired state")
    if not read_oauth_state(state):
        raise HTTPException(400, "Invalid or expired state")

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
        # No user/actor to attach yet (auth itself failed) — still record the attempt so a
        # spike of failed logins is visible in the audit trail rather than leaving no trace.
        audit.record(db, actor_id=None, action=Action.LOGIN_FAILED,
                     metadata={"reason": str(e)})
        db.commit()
        raise HTTPException(401, f"Authentication failed: {e}")

    user = users_service.upsert_from_identity(
        db,
        entra_oid=claims.entra_oid,
        email=claims.email,
        display_name=claims.display_name,
        department=claims.department,
    )

    audit.record(db, actor_id=user.id, action=Action.LOGIN,
                 metadata={"email": user.email})
    db.commit()

    token = issue_session(user.entra_object_id, user.session_version)
    redirect = RedirectResponse(settings.FRONTEND_BASE_URL)
    redirect.delete_cookie(OAUTH_STATE_COOKIE_NAME)
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