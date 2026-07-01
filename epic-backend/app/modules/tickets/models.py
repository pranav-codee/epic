"""Ticket, TicketComment, TicketAttachment — matches SRS Appendix B class diagram."""
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, BigInteger, Integer, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from ...database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


CATEGORIES = ["HARDWARE", "SOFTWARE", "NETWORK", "VPN", "EMAIL", "SECURITY", "ACCESS", "APPLICATION", "OTHER"]
PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
STATUSES = ["OPEN", "ASSIGNED", "IN_PROGRESS", "PENDING_USER", "RESOLVED", "CLOSED", "CANCELLED"]


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(String(36), primary_key=True, default=_uuid)
    ticket_number = Column(String(24), unique=True, nullable=False, index=True)
    creator_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=False, index=True)
    assignee_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True, index=True)
    category = Column(String(32), nullable=False)
    priority = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="OPEN")
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    creator = relationship("UserProfile", foreign_keys=[creator_id])
    assignee = relationship("UserProfile", foreign_keys=[assignee_id])
    comments = relationship("TicketComment", cascade="all, delete-orphan", back_populates="ticket")
    attachments = relationship("TicketAttachment", cascade="all, delete-orphan", back_populates="ticket")

    __table_args__ = (
        Index("ix_tickets_creator_status", "creator_id", "status"),
        Index("ix_tickets_assignee_status", "assignee_id", "status"),
        Index("ix_tickets_status_priority", "status", "priority"),
        Index("ix_tickets_category", "category"),
    )


class TicketCounter(Base):
    """Year-scoped monotonic counter so EPIC-YYYY-NNNNNN stays unique without contention."""
    __tablename__ = "ticket_counters"
    year = Column(Integer, primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)


class TicketComment(Base):
    __tablename__ = "ticket_comments"
    id = Column(String(36), primary_key=True, default=_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    ticket = relationship("Ticket", back_populates="comments")
    author = relationship("UserProfile")


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"
    id = Column(String(36), primary_key=True, default=_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=False, index=True)
    uploaded_by = Column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    file_name = Column(String(256), nullable=False)
    content_type = Column(String(128), nullable=True)
    size_bytes = Column(BigInteger, nullable=False)
    storage_uri = Column(String(512), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    ticket = relationship("Ticket", back_populates="attachments")
