"""TicketAuditLog — insert-only at the ORM layer (REQ-4.8-8)."""
from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger, Integer, Text
from datetime import datetime
from ...database import Base


class TicketAuditLog(Base):
    __tablename__ = "ticket_audit_logs"
    # SQLite auto-increments only when the PK type resolves to INTEGER.
    id = Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True)
    action = Column(String(64), nullable=False)
    field = Column(String(64), nullable=True)
    old_value = Column(String(256), nullable=True)
    new_value = Column(String(256), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
