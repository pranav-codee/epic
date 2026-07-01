from sqlalchemy.orm import Session
from .models import KnowledgeBaseArticle


def list_articles(db: Session, q: str | None = None, category: str | None = None):
    query = db.query(KnowledgeBaseArticle).filter(KnowledgeBaseArticle.published == True)  # noqa: E712
    if q:
        like = f"%{q}%"
        query = query.filter((KnowledgeBaseArticle.title.like(like)) | (KnowledgeBaseArticle.tags.like(like)))
    if category:
        query = query.filter(KnowledgeBaseArticle.category == category)
    return query.order_by(KnowledgeBaseArticle.title).all()


def get_by_slug_or_id(db: Session, identifier: str):
    return (db.query(KnowledgeBaseArticle)
              .filter((KnowledgeBaseArticle.id == identifier) | (KnowledgeBaseArticle.slug == identifier))
              .one_or_none())
