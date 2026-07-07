from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from . import service
from .schemas import UserProfileOut, RoleUpdateIn
from ...database import get_db
from ...dependencies import get_current_user
from ...core.rbac import require_role, Role

router = APIRouter()


@router.get("", response_model=list[UserProfileOut])
def list_users(q: str | None = None, db: Session = Depends(get_db),
               _admin=Depends(require_role(Role.SYSTEM_ADMIN))):
    users = service.list_users(db, q=q)
    return [service.attach_roles(u, db) for u in users]


@router.get("/{user_id}", response_model=UserProfileOut)
def get_user(user_id: str, db: Session = Depends(get_db), me=Depends(get_current_user)):
    # Self or admin can read.
    is_admin = Role.SYSTEM_ADMIN.value in (me.roles or [])
    if user_id != me.id and not is_admin:
        raise HTTPException(403, "Forbidden")
    user = service.get_user(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return service.attach_roles(user, db)


@router.patch("/{user_id}/roles", response_model=UserProfileOut)
def update_roles(user_id: str, payload: RoleUpdateIn, db: Session = Depends(get_db),
                 _admin=Depends(require_role(Role.SYSTEM_ADMIN))):
    try:
        user = service.set_roles(db, user_id, payload.roles)
        # A role change is a privilege change — force any existing session cookie to be
        # re-validated rather than letting an old (now-wrong) privilege level ride out its 8h.
        service.revoke_sessions(db, user_id)
    except (ValueError, LookupError) as e:
        raise HTTPException(400, str(e))
    return service.attach_roles(user, db)


@router.post("/{user_id}/revoke-sessions", status_code=204)
def force_logout(user_id: str, db: Session = Depends(get_db),
                 _admin=Depends(require_role(Role.SYSTEM_ADMIN))):
    """Immediately invalidates every session cookie currently held by this user."""
    try:
        service.revoke_sessions(db, user_id)
    except LookupError as e:
        raise HTTPException(404, str(e))