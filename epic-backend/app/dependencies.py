"""
Shared FastAPI dependencies: get_db (re-exported), get_current_user from session cookie.
"""
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session
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

    oid = read_session(epic_session)
    if not oid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    # Imported here to avoid circular import at module-load time.
    from .modules.users.models import UserProfile, UserRoleAssignment

    user = db.query(UserProfile).filter(UserProfile.entra_object_id == oid).one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile not found or inactive")

    # Attach role strings as a transient attribute.
    user.roles = [r.role for r in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).all()]
    return user
