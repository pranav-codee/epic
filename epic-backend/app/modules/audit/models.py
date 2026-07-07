"""TicketAuditLog — insert-only at the ORM layer (REQ-4.8-8).

`ticket_id` is nullable because this log is also the system-wide security audit trail:
account/role events (role grants/revocations, forced session revocation, logins) have no
associated ticket, but still need a tamper-evident, insert-only record (A09 - Security
Logging and Monitoring Failure). Non-ticket events use the `action` values defined in
audit/service.py (ROLE_GRANT, ROLE_REVOKE, FORCE_LOGOUT, LOGIN, LOGIN_FAILED)."""
from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger, Integer, Text, Index
from datetime import datetime
from ...database import Base


class TicketAuditLog(Base):
    __tablename__ = "ticket_audit_logs"
    # SQLite auto-increments only when the PK type resolves to INTEGER.
    id = Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=True, index=True)
    actor_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True)
    action = Column(String(64), nullable=False)
    field = Column(String(64), nullable=True)
    old_value = Column(String(256), nullable=True)
    new_value = Column(String(256), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_actor_action", "actor_id", "action"),
        Index("ix_audit_action_created", "action", "created_at"),
    )