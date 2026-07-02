from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from .models import CATEGORIES, PRIORITIES, STATUSES, TICKET_TYPES


class TicketCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=256)
    description: str = Field(min_length=5)
    ticket_type: str
    category: str
    priority: str

    def normalized(self):
        self.ticket_type = self.ticket_type.upper().strip()
        self.category = self.category.upper().strip()
        self.priority = self.priority.upper().strip()
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
    creator: Optional[UserBrief] = None
    assignee: Optional[UserBrief] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TicketDetailOut(TicketOut):
    comments: List[TicketCommentOut] = []
    attachments: List[TicketAttachmentOut] = []
    allowed_target_states: List[str] = []