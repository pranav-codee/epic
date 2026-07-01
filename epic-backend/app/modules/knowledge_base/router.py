"""
Read-only Knowledge Base (REQ-4.4-3). No authoring endpoints. Content is loaded out-of-band
via scripts/seed_kb.py per TBD-5.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from . import service
from .schemas import KBArticleBrief, KBArticleOut
from ...database import get_db
from ...dependencies import get_current_user

router = APIRouter()


@router.get("/articles", response_model=list[KBArticleBrief])
def list_articles(q: str | None = None, category: str | None = None,
                  db: Session = Depends(get_db), _me=Depends(get_current_user)):
    return service.list_articles(db, q=q, category=category)


@router.get("/articles/{identifier}", response_model=KBArticleOut)
def get_article(identifier: str, db: Session = Depends(get_db), _me=Depends(get_current_user)):
    art = service.get_by_slug_or_id(db, identifier)
    if not art or not art.published:
        raise HTTPException(404, "Article not found")
    return art
