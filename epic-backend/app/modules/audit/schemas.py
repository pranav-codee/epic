from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AuditEntryOut(BaseModel):
    id: int
    ticket_id: str
    actor_id: Optional[str] = None
    action: str
    field: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
