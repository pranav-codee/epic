import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from datetime import datetime
from ...database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class NotificationRecord(Base):
    __tablename__ = "notification_records"
    id = Column(String(36), primary_key=True, default=_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=True, index=True)
    recipient_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True)
    channel = Column(String(32), nullable=False, default="TEAMS")
    event = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="PENDING")  # PENDING | SENT | FAILED | SKIPPED
    payload_json = Column(Text, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
