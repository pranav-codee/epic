from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from .models import CATEGORIES, PRIORITIES, STATUSES, TICKET_TYPES, CHANNELS


class TicketCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=256)
    description: str = Field(min_length=5)
    ticket_type: str
    category: str
    priority: str
    # SPEC §1 additions — all optional, defaulted server-side when omitted.
    requestor_id: Optional[str] = None
    location_id: Optional[str] = None
    channel: Optional[str] = None
    device_name: Optional[str] = None
    device_ip_address: Optional[str] = None
    device_site_name: Optional[str] = None

    def normalized(self):
        self.ticket_type = self.ticket_type.upper().strip()
        self.category = self.category.upper().strip()
        self.priority = self.priority.upper().strip()
        if self.channel:
            self.channel = self.channel.upper().strip()
            if self.channel not in CHANNELS:
                raise ValueError(f"Invalid channel. Allowed: {CHANNELS}")
        if self.ticket_type not in TICKET_TYPES:
            raise ValueError(f"Invalid ticket_type. Allowed: {TICKET_TYPES}")
        if self.category not in CATEGORIES:
            raise ValueError(f"Invalid category. Allowed: {CATEGORIES}")
        if self.priority not in PRIORITIES:
            raise ValueError(f"Invalid priority. Allowed: {PRIORITIES}")
        return self


class TicketAssignIn(BaseModel):
    assignee_id: str


class StatusChangeIn(BaseModel):
    target_status: str


class WorkflowStatusChangeIn(BaseModel):
    """SPEC §3: target for the ticket-type-specific workflow (distinct from StatusChangeIn's
    `target_status`, which drives the pre-existing generic `status` field)."""
    target_workflow_status: str


class PriorityChangeIn(BaseModel):
    priority: str


class TicketTypeChangeIn(BaseModel):
    ticket_type: str


class CommentCreateIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class UserBrief(BaseModel):
    id: str
    display_name: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True


class TicketCommentOut(BaseModel):
    id: str
    text: str
    author: Optional[UserBrief] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TicketAttachmentOut(BaseModel):
    id: str
    file_name: str
    content_type: Optional[str] = None
    size_bytes: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


class TicketOut(BaseModel):
    id: str
    ticket_number: str
    title: str
    description: str
    ticket_type: str
    category: str
    priority: str
    status: str
    # SPEC §3 — additive alongside `status`; see workflow.py module docstring. NULL for
    # PROBLEM/CHANGE_REQUEST tickets and any ticket predating this column.
    workflow_status: Optional[str] = None
    sla_paused_at: Optional[datetime] = None
    sla_paused_total_seconds: int = 0
    creator: Optional[UserBrief] = None
    requestor: Optional[UserBrief] = None
    assignee: Optional[UserBrief] = None
    location_id: Optional[str] = None
    assignment_group_id: Optional[str] = None
    channel: str = "SELF_SERVICE"
    device_name: Optional[str] = None
    device_ip_address: Optional[str] = None
    device_site_name: Optional[str] = None
    vendor_ticket_id: Optional[str] = None
    is_from_email_mgr: Optional[bool] = None
    created_at: datetime
    updated_at: datetime
    first_response_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    sla_due_at: Optional[datetime] = None
    response_sla_status: Optional[str] = None
    resolution_sla_status: Optional[str] = None
    breached_reason: Optional[str] = None
    sla_status: str = "NONE"
    # Set once by app.core.sla_scanner the first time this ticket is observed AT_RISK/BREACHED —
    # non-NULL means "an escalation notification for this state has already gone out." Exposed
    # so the ticket detail UI can show escalation history, not just the current computed status.
    sla_at_risk_notified_at: Optional[datetime] = None
    sla_breached_notified_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TicketDetailOut(TicketOut):
    comments: List[TicketCommentOut] = []
    attachments: List[TicketAttachmentOut] = []
    allowed_target_states: List[str] = []
    # SPEC §3 — direct workflow_status targets reachable from the ticket's current
    # workflow_status, for UI button rendering (mirrors allowed_target_states above, which
    # covers the pre-existing generic `status` field). Empty for ticket types with no §3
    # workflow (PROBLEM/CHANGE_REQUEST) or a ticket already in a terminal legacy status.
    allowed_workflow_target_states: List[str] = []