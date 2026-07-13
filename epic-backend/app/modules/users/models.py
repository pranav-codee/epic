"""User profile + role assignment. Matches SRS Appendix B class diagram."""
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from ...database import Base
from ...core.time import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


# Vendor user type (SPEC §2): distinct from internal employees — legacy pattern like
# "FMS Egypt" (a queue label, not a named person). Gets a restricted *default* permission
# set once the dynamic permission registry lands (SPEC §5) — this is not a hard cap, and
# no permission logic is wired to this field yet; it's the foundation column only.
USER_TYPES = ["INTERNAL", "VENDOR"]


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(String(36), primary_key=True, default=_uuid)
    entra_object_id = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=False, index=True)
    display_name = Column(String(256), nullable=True)
    department = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    user_type = Column(String(16), nullable=False, default="INTERNAL", server_default="INTERNAL")
    # SPEC §1: ticket.location is auto-filled from the creator's home_location at creation
    # (still editable/overridable afterward on the ticket itself). Nullable for now since
    # existing users/tests predate this field and there's no historical-location data to
    # backfill from (SPEC §10: no historical data migration).
    home_location_id = Column(String(36), ForeignKey("locations.id"), nullable=True, index=True)
    # Bumped whenever we need to invalidate all of this user's existing session cookies
    # immediately (e.g. "force logout", suspicious activity, deactivation) rather than
    # waiting out the 8h natural expiry. The value is embedded in the signed session token
    # and checked against the DB on every request.
    session_version = Column(String(36), default=_uuid, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    role_assignments = relationship("UserRoleAssignment", cascade="all, delete-orphan", backref="user")
    home_location = relationship("Location", foreign_keys=[home_location_id])
    assignment_groups = relationship("UserAssignmentGroup", cascade="all, delete-orphan",
                                     backref="user_profile")


class UserRoleAssignment(Base):
    __tablename__ = "user_roles"
    user_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    role = Column(String(32), nullable=False)   # EMPLOYEE | IT_ENGINEER | IT_MANAGER | SYSTEM_ADMIN
    __table_args__ = (PrimaryKeyConstraint("user_id", "role", name="pk_user_role"),)