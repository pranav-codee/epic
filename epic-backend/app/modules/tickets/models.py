"""Ticket, TicketComment, TicketAttachment — matches SRS Appendix B class diagram."""
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, BigInteger, Integer, Index
from sqlalchemy.orm import relationship
from ...database import Base
from ...core.sla import sla_status as _compute_sla_status
from ...core.time import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


CATEGORIES = ["HARDWARE", "SOFTWARE", "NETWORK", "VPN", "EMAIL", "SECURITY", "ACCESS", "APPLICATION", "OTHER"]
PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
STATUSES = ["OPEN", "ASSIGNED", "IN_PROGRESS", "PENDING_USER", "RESOLVED", "CLOSED", "CANCELLED"]

# ITIL-aligned ticket classification (REQ: ticket type taxonomy).
# INCIDENT: unplanned interruption/degradation of an IT service.
# SERVICE_REQUEST: routine, planned request for new service/hardware/access (no disruption).
# PROBLEM: investigation into the root cause of one or more related incidents.
# CHANGE_REQUEST: formal, planned modification to IT infrastructure.
TICKET_TYPES = ["INCIDENT", "SERVICE_REQUEST", "PROBLEM", "CHANGE_REQUEST"]


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(String(36), primary_key=True, default=_uuid)
    ticket_number = Column(String(24), unique=True, nullable=False, index=True)
    creator_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=False, index=True)
    assignee_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True, index=True)
    ticket_type = Column(String(24), nullable=False, default="INCIDENT", server_default="INCIDENT")
    category = Column(String(32), nullable=False)
    priority = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="OPEN")
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    # SLA (Service Level Agreement) target resolution deadline, set at creation time
    # (and refreshed on priority change) from app.core.sla.SLA_HOURS_BY_PRIORITY.
    sla_due_at = Column(DateTime, nullable=True)
    # Set (once) by app.core.sla_scanner the first time this ticket is observed
    # AT_RISK / BREACHED. A non-NULL value means "don't send this escalation again."
    # Both reset to NULL whenever sla_due_at is recomputed (see change_priority in
    # tickets/service.py) so a re-prioritized ticket gets a fresh notification cycle
    # instead of being permanently "already notified" from its old SLA window.
    sla_at_risk_notified_at = Column(DateTime, nullable=True)
    sla_breached_notified_at = Column(DateTime, nullable=True)

    creator = relationship("UserProfile", foreign_keys=[creator_id])
    assignee = relationship("UserProfile", foreign_keys=[assignee_id])
    comments = relationship("TicketComment", cascade="all, delete-orphan", back_populates="ticket")
    attachments = relationship("TicketAttachment", cascade="all, delete-orphan", back_populates="ticket")

    __table_args__ = (
        Index("ix_tickets_creator_status", "creator_id", "status"),
        Index("ix_tickets_assignee_status", "assignee_id", "status"),
        Index("ix_tickets_status_priority", "status", "priority"),
        Index("ix_tickets_category", "category"),
        Index("ix_tickets_ticket_type", "ticket_type"),
    )

    @property
    def sla_status(self) -> str:
        """One of NONE, ON_TRACK, AT_RISK, BREACHED, MET — derived, never stored directly
        so it's always accurate as of "now" rather than going stale."""
        return _compute_sla_status(
            priority=self.priority,
            created_at=self.created_at,
            sla_due_at=self.sla_due_at,
            resolved_at=self.resolved_at,
            closed_at=self.closed_at,
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
    created_at = Column(DateTime, default=utcnow, nullable=False)

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
    uploaded_at = Column(DateTime, default=utcnow, nullable=False)

    ticket = relationship("Ticket", back_populates="attachments")