from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class KBArticleBrief(BaseModel):
    id: str
    title: str
    slug: str
    category: Optional[str] = None
    tags: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class KBArticleOut(KBArticleBrief):
    content: str
