"""
User profile management. The primary call site is `upsert_from_identity(...)` which is
invoked by the auth callback after Entra ID has authenticated the user.
"""
import uuid
from sqlalchemy.orm import Session
from .models import UserProfile, UserRoleAssignment
from ...config import get_settings
from ...core.rbac import Role
from ...core.time import utcnow
from ..audit import service as audit
from ..audit.service import Action


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

    user.last_login_at = utcnow()
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


def list_support_staff(db: Session, limit: int = 200):
    """Narrower than list_users(): returns only users holding IT_ENGINEER/IT_MANAGER/
    SYSTEM_ADMIN, for populating ticket-assignment dropdowns. Any IT staff member may call
    this (see users/router.py) — unlike list_users(), which stays SYSTEM_ADMIN-only since it
    exposes every employee's email/department and shouldn't be widened just to support the
    assign-ticket UI (data minimization, DPDP)."""
    support_roles = {Role.IT_ENGINEER.value, Role.IT_MANAGER.value, Role.SYSTEM_ADMIN.value}
    user_ids = {row[0] for row in db.query(UserRoleAssignment.user_id)
                .filter(UserRoleAssignment.role.in_(support_roles)).all()}
    if not user_ids:
        return []
    return (db.query(UserProfile)
              .filter(UserProfile.id.in_(user_ids))
              .order_by(UserProfile.display_name)
              .limit(limit).all())


def _system_admin_holder_ids(db: Session, *, exclude_user_id: str | None = None) -> set[str]:
    q = db.query(UserRoleAssignment.user_id).filter(UserRoleAssignment.role == Role.SYSTEM_ADMIN.value)
    if exclude_user_id:
        q = q.filter(UserRoleAssignment.user_id != exclude_user_id)
    return {row[0] for row in q.all()}


def set_roles(db: Session, user_id: str, roles: list[str], *, actor_id: str | None = None) -> UserProfile:
    invalid = [r for r in roles if r not in VALID_ROLES]
    if invalid:
        raise ValueError(f"Invalid role(s): {invalid}. Valid: {sorted(VALID_ROLES)}")

    user = db.query(UserProfile).filter(UserProfile.id == user_id).one_or_none()
    if not user:
        raise LookupError("User not found")

    current_roles = {r.role for r in db.query(UserRoleAssignment)
                      .filter(UserRoleAssignment.user_id == user_id).all()}
    new_roles = set(roles)

    # Guardrail (Broken Access Control): if this user currently holds SYSTEM_ADMIN and the
    # new role set would drop it, make sure at least one *other* SYSTEM_ADMIN still exists.
    # Without this, the last admin (including via self-service on their own account) can
    # permanently lock the whole application out of admin-only actions — there is no other
    # way to grant SYSTEM_ADMIN back short of a direct database edit.
    if Role.SYSTEM_ADMIN.value in current_roles and Role.SYSTEM_ADMIN.value not in new_roles:
        remaining_admins = _system_admin_holder_ids(db, exclude_user_id=user_id)
        if not remaining_admins:
            raise ValueError(
                "Cannot remove the SYSTEM_ADMIN role from the last remaining system "
                "administrator. Grant SYSTEM_ADMIN to another user first."
            )

    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id).delete()
    db.flush()
    for r in new_roles:
        db.add(UserRoleAssignment(user_id=user_id, role=r))

    added = sorted(new_roles - current_roles)
    removed = sorted(current_roles - new_roles)
    if added:
        audit.record(db, actor_id=actor_id, action=Action.ROLE_GRANT,
                     field="roles", old_value=None, new_value=",".join(added),
                     metadata={"target_user_id": user_id, "added": added})
    if removed:
        audit.record(db, actor_id=actor_id, action=Action.ROLE_REVOKE,
                     field="roles", old_value=",".join(removed), new_value=None,
                     metadata={"target_user_id": user_id, "removed": removed})

    db.commit()
    db.refresh(user)
    return user


def revoke_sessions(db: Session, user_id: str, *, actor_id: str | None = None,
                    reason: str = "FORCE_LOGOUT") -> UserProfile:
    """Force-logout: any session cookie issued before this call stops working immediately,
    instead of waiting out the normal 8h expiry."""
    user = db.query(UserProfile).filter(UserProfile.id == user_id).one_or_none()
    if not user:
        raise LookupError("User not found")
    user.session_version = str(uuid.uuid4())
    audit.record(db, actor_id=actor_id, action=Action.FORCE_LOGOUT,
                 field="session_version", metadata={"target_user_id": user_id, "reason": reason})
    db.commit()
    db.refresh(user)
    return user


def attach_roles(user: UserProfile, db: Session) -> UserProfile:
    """Attach roles as a list on the transient .roles attribute (used by API serializers)."""
    user.roles = [r.role for r in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).all()]
    return user


def set_home_location(db: Session, user_id: str, location_id: str, *, actor_id: str | None = None) -> UserProfile:
    """SPEC §1: user.home_location feeds ticket auto-fill at creation. Self-service (any
    user may set their own) or admin-set for someone else — the router enforces that."""
    from ..catalogue.models import Location
    user = db.query(UserProfile).filter(UserProfile.id == user_id).one_or_none()
    if not user:
        raise LookupError("User not found")
    loc = db.query(Location).filter(Location.id == location_id, Location.is_active.is_(True)).one_or_none()
    if not loc:
        raise ValueError("Location not found or inactive")
    user.home_location_id = loc.id
    db.commit()
    db.refresh(user)
    return user