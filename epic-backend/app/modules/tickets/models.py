"""Ticket, TicketComment, TicketAttachment — matches SRS Appendix B class diagram."""
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, BigInteger, Integer, Index, Boolean
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

# SPEC §1 additions below.
CHANNELS = ["EMAIL", "PHONE", "MONITORING_TOOL", "SELF_SERVICE"]
SLA_STATUSES = ["MET", "BREACHED"]  # full Met/Breached logic lands with the SLA phase (SPEC §4)


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(String(36), primary_key=True, default=_uuid)
    ticket_number = Column(String(24), unique=True, nullable=False, index=True)
    # `creator_id` is SPEC's `created_by` (the agent/person who logged the ticket in the
    # system — may act on someone else's behalf). `requestor_id` is the person the ticket is
    # actually *for*, and defaults to creator_id when not explicitly set (SPEC §1: "requestor
    # vs created_by — two distinct people"). Nullable so existing rows/tests aren't broken;
    # service.create_ticket backfills it to creator_id when omitted.
    creator_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=False, index=True)
    requestor_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True, index=True)
    assignee_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=True, index=True)
    ticket_type = Column(String(24), nullable=False, default="INCIDENT", server_default="INCIDENT")
    category = Column(String(32), nullable=False)
    priority = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="OPEN")
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)

    # --- SPEC §3: ticket-type-specific workflow status ---
    # Additive alongside `status` above (see workflow.py module docstring for why the two
    # coexist). NULL for ticket types SPEC §3 doesn't define a workflow for
    # (PROBLEM/CHANGE_REQUEST) and, transiently, for any pre-existing row created before this
    # column existed. INCIDENT/SERVICE_REQUEST tickets get it populated at creation time.
    workflow_status = Column(String(24), nullable=True, index=True)

    # --- SPEC §1: location ---
    # Required per spec, auto-filled from the creator's home_location at ticket creation but
    # editable/overridable afterward. Left nullable at the DB level this session (existing
    # dev/test tickets and users predate home_location; SPEC §10 rules out a historical
    # backfill migration) — service.create_ticket already populates it whenever the creator
    # has a home_location, and enforcing NOT NULL is planned once every active user has one.
    location_id = Column(String(36), ForeignKey("locations.id"), nullable=True, index=True)

    # --- SPEC §1: 3-level classification hierarchy (Tower -> Service -> Item) ---
    # Additive alongside the existing flat `category` string column above (kept for backward
    # compatibility with the current state machine/tests/frontend this session) — cutting
    # over ticket creation to require the hierarchy and retiring the flat enum is later-session
    # work, see /PROGRESS.md.
    category_id = Column(String(36), ForeignKey("catalogue_categories.id"), nullable=True, index=True)
    subcategory_id = Column(String(36), ForeignKey("catalogue_subcategories.id"), nullable=True, index=True)
    item_id = Column(String(36), ForeignKey("catalogue_items.id"), nullable=True, index=True)

    # --- SPEC §1: channel + monitoring-tool fields ---
    channel = Column(String(24), nullable=False, default="SELF_SERVICE", server_default="SELF_SERVICE")
    # Only populated for channel == MONITORING_TOOL tickets (SPEC §6's future ingestion
    # endpoint); nullable for every other channel.
    device_name = Column(String(256), nullable=True)
    device_ip_address = Column(String(64), nullable=True)
    device_site_name = Column(String(256), nullable=True)

    # --- SPEC §2: routing target ---
    # Required per spec ("a ticket belongs to exactly one group"); nullable this session
    # since the routing engine that assigns a default group (SPEC §6) isn't built yet, so
    # tickets created via the current flow have nowhere to be auto-routed to. Enforce NOT
    # NULL once §6 lands.
    assignment_group_id = Column(String(36), ForeignKey("assignment_groups.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    # `resolved_at` already existed; `first_response_at` is new (SPEC §1: "two independent
    # timestamps"). Both are populated by later SLA-phase logic (SPEC §4) — just the columns
    # for now.
    first_response_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    # --- SPEC §4 Part 2: business-hours Response/Resolution due timestamps ---
    # Computed at creation (and refreshed on priority change) via
    # app.core.sla.compute_business_hours_sla_due_dates — the Part 1 business-hours
    # engine — in the ticket's location's local timezone, instead of the old 24/7
    # SLA_HOURS_BY_PRIORITY/compute_due_at path. Independent per SPEC §4 ("Independent
    # Response + Resolution clocks") — each is its own column, each computed separately
    # from the same start time.
    response_due_at = Column(DateTime, nullable=True)
    resolution_due_at = Column(DateTime, nullable=True)

    # --- SPEC §1: independent response/resolution SLA status fields ---
    # NULL means "not yet evaluated". SPEC §4 Part 2 (this session) now actually sets
    # these: response_sla_status on first response (tickets/service.py's
    # _record_first_response), resolution_sla_status on resolution
    # (_record_resolution). See /PROGRESS.md Session 4 for the "first response"
    # definition this session settled on.
    response_sla_status = Column(String(16), nullable=True)
    resolution_sla_status = Column(String(16), nullable=True)
    # Free text, required server-side (app-layer, not a DB constraint) once either SLA status
    # above is BREACHED — that validation belongs with the SLA-phase logic in SPEC §4.
    breached_reason = Column(Text, nullable=True)

    # --- SPEC §3: "Resolution SLA clock pauses during PEND_USER/PEND_3RDPARTY" ---
    # This session implements the pause/resume *bookkeeping* only — not the business-hours
    # SLA calculation itself (that's SPEC §4, still a later session). `sla_paused_at` is the
    # timestamp the ticket most recently entered a pause workflow_status, or NULL when not
    # currently paused. `sla_paused_total_seconds` accumulates the total time spent paused
    # across the ticket's lifetime, so whenever §4's business-hours engine lands it has
    # everything it needs to subtract paused time from the resolution clock without having to
    # replay the full audit-log history.
    sla_paused_at = Column(DateTime, nullable=True)
    sla_paused_total_seconds = Column(Integer, nullable=False, default=0, server_default="0")

    # --- SPEC §1: misc nullable flags ---
    vendor_ticket_id = Column(String(64), nullable=True)
    is_from_email_mgr = Column(Boolean, nullable=True)
    # Legacy alias: kept in sync with `resolution_due_at` above (same value, every time
    # it's set) purely so the pre-existing `Ticket.sla_status` property below and
    # SPEC §8's (not-yet-built) reporting/export code — which both still read
    # `sla_due_at` specifically — keep working unchanged. New SPEC §4 code should read
    # `response_due_at`/`resolution_due_at` directly instead of this column.
    sla_due_at = Column(DateTime, nullable=True)
    # SPEC §4 Part 2 (this session): these two now represent the *Resolution* clock's
    # scanner notification bookkeeping specifically — app.core.sla_scanner scans the
    # Response and Resolution clocks independently, and the Response clock gets its own
    # pair of columns below rather than overloading these further. (Before this session
    # there was only one clock, so these columns' meaning was unambiguous; SPEC §4 Part 2
    # narrows what they mean without needing a rename/migration, since "the ticket's
    # overall due-date scan" *is* the Resolution clock once Response is split out.)
    # Set (once) the first time this ticket is observed AT_RISK / BREACHED on its
    # Resolution clock. A non-NULL value means "don't send this escalation again."
    # Both reset to NULL whenever sla_due_at is recomputed (see change_priority in
    # tickets/service.py) so a re-prioritized ticket gets a fresh notification cycle
    # instead of being permanently "already notified" from its old SLA window.
    sla_at_risk_notified_at = Column(DateTime, nullable=True)
    sla_breached_notified_at = Column(DateTime, nullable=True)
    # --- SPEC §4 Part 2: Response clock's own scanner notification bookkeeping ---
    # Mirrors sla_at_risk_notified_at/sla_breached_notified_at immediately above (now the
    # Resolution clock's columns) but tracked separately for the Response clock, since
    # SPEC §4 requires the two clocks to be scanned independently and a ticket can be
    # AT_RISK/BREACHED on one without being anywhere near the other.
    response_sla_at_risk_notified_at = Column(DateTime, nullable=True)
    response_sla_breached_notified_at = Column(DateTime, nullable=True)

    creator = relationship("UserProfile", foreign_keys=[creator_id])
    requestor = relationship("UserProfile", foreign_keys=[requestor_id])
    assignee = relationship("UserProfile", foreign_keys=[assignee_id])
    location = relationship("Location", foreign_keys=[location_id])
    catalogue_category = relationship("CatalogueCategory", foreign_keys=[category_id])
    catalogue_subcategory = relationship("CatalogueSubcategory", foreign_keys=[subcategory_id])
    catalogue_item = relationship("CatalogueItem", foreign_keys=[item_id])
    assignment_group = relationship("AssignmentGroup", foreign_keys=[assignment_group_id])
    comments = relationship("TicketComment", cascade="all, delete-orphan", back_populates="ticket")
    attachments = relationship("TicketAttachment", cascade="all, delete-orphan", back_populates="ticket")

    __table_args__ = (
        Index("ix_tickets_creator_status", "creator_id", "status"),
        Index("ix_tickets_assignee_status", "assignee_id", "status"),
        Index("ix_tickets_status_priority", "status", "priority"),
        Index("ix_tickets_category", "category"),
        Index("ix_tickets_ticket_type", "ticket_type"),
        Index("ix_tickets_assignment_group", "assignment_group_id", "status"),
        Index("ix_tickets_location", "location_id"),
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