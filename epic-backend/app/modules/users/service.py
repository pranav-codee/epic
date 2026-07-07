"""
User profile management. The primary call site is `upsert_from_identity(...)` which is
invoked by the auth callback after Entra ID has authenticated the user.
"""
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from .models import UserProfile, UserRoleAssignment
from ...config import get_settings
from ...core.rbac import Role


VALID_ROLES = {r.value for r in Role}


def upsert_from_identity(db: Session, *, entra_oid: str, email: str, display_name: str, department: str | None = None) -> UserProfile:
    """Create or update a user profile from an identity-provider claim set."""
    settings = get_settings()
    user = db.query(UserProfile).filter(UserProfile.entra_object_id == entra_oid).one_or_none()

    if user is None:
        user = UserProfile(
            entra_object_id=entra_oid,
            email=email,
            display_name=display_name,
            department=department,
            is_active=True,
        )
        db.add(user)
        db.flush()

        # Every new user gets the EMPLOYEE role.
        db.add(UserRoleAssignment(user_id=user.id, role=Role.EMPLOYEE.value))

        # Bootstrap admin emails get SYSTEM_ADMIN on first login (configurable).
        if email.lower() in settings.bootstrap_admin_emails_set:
            db.add(UserRoleAssignment(user_id=user.id, role=Role.SYSTEM_ADMIN.value))
    else:
        user.email = email
        user.display_name = display_name
        user.department = department or user.department

    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: str) -> UserProfile | None:
    return db.query(UserProfile).filter(UserProfile.id == user_id).one_or_none()


def list_users(db: Session, q: str | None = None, limit: int = 100):
    query = db.query(UserProfile)
    if q:
        like = f"%{q}%"
        query = query.filter((UserProfile.email.like(like)) | (UserProfile.display_name.like(like)))
    return query.order_by(UserProfile.display_name).limit(limit).all()


def set_roles(db: Session, user_id: str, roles: list[str]) -> UserProfile:
    invalid = [r for r in roles if r not in VALID_ROLES]
    if invalid:
        raise ValueError(f"Invalid role(s): {invalid}. Valid: {sorted(VALID_ROLES)}")

    user = db.query(UserProfile).filter(UserProfile.id == user_id).one_or_none()
    if not user:
        raise LookupError("User not found")

    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id).delete()
    db.flush()
    for r in set(roles):
        db.add(UserRoleAssignment(user_id=user_id, role=r))
    db.commit()
    db.refresh(user)
    return user


def revoke_sessions(db: Session, user_id: str) -> UserProfile:
    """Force-logout: any session cookie issued before this call stops working immediately,
    instead of waiting out the normal 8h expiry."""
    user = db.query(UserProfile).filter(UserProfile.id == user_id).one_or_none()
    if not user:
        raise LookupError("User not found")
    user.session_version = str(uuid.uuid4())
    db.commit()
    db.refresh(user)
    return user


def attach_roles(user: UserProfile, db: Session) -> UserProfile:
    """Attach roles as a list on the transient .roles attribute (used by API serializers)."""
    user.roles = [r.role for r in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).all()]
    return user