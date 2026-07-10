from pydantic import BaseModel
from typing import Optional, List
from ..tickets.schemas import TicketOut


class TicketSearchOut(BaseModel):
    total: int
    limit: int
    offset: int
    results: List[TicketOut]
