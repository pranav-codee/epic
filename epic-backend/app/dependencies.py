"""
Shared FastAPI dependencies: get_db (re-exported), get_current_user from session cookie.
"""
import hmac
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from .config import get_settings
from .database import get_db
from .core.security import read_session, SESSION_COOKIE_NAME


def get_current_user(
    db: Session = Depends(get_db),
    epic_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    """
    Resolve the current user from a signed session cookie. Returns the UserProfile ORM object
    with `.roles` populated as a list of role strings for convenience.

    Raises 401 if no/invalid session.
    """
    if not epic_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session_data = read_session(epic_session)
    if not session_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    oid = session_data["oid"]

    # Imported here to avoid circular import at module-load time.
    from .modules.users.models import UserProfile, UserRoleAssignment

    user = db.query(UserProfile).filter(UserProfile.entra_object_id == oid).one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile not found or inactive")
    if session_data.get("sv") != user.session_version:
        # The token predates a forced revocation (deactivation, admin "log out everywhere",
        # role change, etc). Reject even though the signature itself is still valid.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

    # Attach role strings as a transient attribute.
    user.roles = [r.role for r in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).all()]
    return user


def require_monitoring_ingest_token(
    authorization: str | None = Header(default=None),
):
    """
    SPEC §6 / §9: auth for the dedicated monitoring-tool ticket-ingestion endpoint. This is
    machine-to-machine traffic (a monitoring tool, not a signed-in human), so — deliberately,
    unlike every other tickets/* route — this does NOT use get_current_user's session-cookie
    flow. Instead it checks a static service-token bearer credential (MONITORING_INGEST_TOKEN)
    configured out-of-band via env.

    Fails closed on every branch (SPEC §9): an unconfigured token, a missing/malformed
    Authorization header, or a mismatched token are all a 401 — never a silent pass-through.
    """
    settings = get_settings()
    expected = settings.MONITORING_INGEST_TOKEN
    if not expected:
        # No token has been provisioned for this deployment — treat the endpoint as
        # unusable rather than accepting a blank/empty credential.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Monitoring ingestion is not configured")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing or invalid bearer token")

    token = authorization[len("Bearer "):].strip()
    # Constant-time comparison so response timing can't be used to brute-force the token
    # one byte at a time.
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token")

    return True