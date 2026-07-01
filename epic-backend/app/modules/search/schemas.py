from pydantic import BaseModel
from typing import Optional, List
from ..tickets.schemas import TicketOut


class TicketSearchOut(BaseModel):
    total: int
    results: List[TicketOut]
