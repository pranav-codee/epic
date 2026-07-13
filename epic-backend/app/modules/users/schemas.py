from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class UserProfileOut(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    department: Optional[str] = None
    is_active: bool
    user_type: str = "INTERNAL"
    home_location_id: Optional[str] = None
    roles: List[str] = []
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HomeLocationUpdateIn(BaseModel):
    location_id: str


class RoleUpdateIn(BaseModel):
    roles: List[str]   # full replacement set