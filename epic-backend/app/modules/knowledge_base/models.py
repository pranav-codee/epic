import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text
from ...database import Base
from ...core.time import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


class KnowledgeBaseArticle(Base):
    __tablename__ = "knowledge_base_articles"
    id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String(256), nullable=False)
    slug = Column(String(256), unique=True, nullable=False, index=True)
    content = Column(Text, nullable=False)
    category = Column(String(64), nullable=True)
    tags = Column(String(512), nullable=True)
    published = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)