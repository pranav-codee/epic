import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from ...database import Base
from ...core.time import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


class NotificationRecord(Base):
    __tablename__ = "notification_records"
    id = Column(String(36), primary_key=True, default=_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=True, index=True)
    recipient_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True)
    channel = Column(String(32), nullable=False, default="TEAMS")
    event = Column(String(64), nullable=False)
    # PENDING | SENT | FAILED | RETRYING | DEAD_LETTER | SKIPPED
    status = Column(String(16), nullable=False, default="PENDING")
    payload_json = Column(Text, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    # --- Retry bookkeeping (fixes: failed Teams sends were never retried) ---
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=True, index=True)