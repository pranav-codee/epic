from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class UserProfileOut(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    department: Optional[str] = None
    is_active: bool
    roles: List[str] = []
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleUpdateIn(BaseModel):
    roles: List[str]   # full replacement set