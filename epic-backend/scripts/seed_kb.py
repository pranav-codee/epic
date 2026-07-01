"""Seed Knowledge Base articles from markdown files. Usage: python scripts/seed_kb.py ./kb_content/"""
import sys, os, re, uuid
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.modules.knowledge_base.models import KnowledgeBaseArticle


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main(path: str = "./kb_content"):
    if not os.path.isdir(path):
        print(f"Directory not found: {path}"); return
    db = SessionLocal()
    try:
        for fn in os.listdir(path):
            if not fn.endswith(".md"):
                continue
            with open(os.path.join(path, fn), "r", encoding="utf-8") as f:
                content = f.read()
            title = fn[:-3].replace("_", " ").title()
            slug = slugify(title)
            existing = db.query(KnowledgeBaseArticle).filter_by(slug=slug).one_or_none()
            if existing:
                existing.content = content
                existing.updated_at = datetime.utcnow()
            else:
                db.add(KnowledgeBaseArticle(id=str(uuid.uuid4()), title=title, slug=slug,
                                            content=content, category="General", published=True))
        db.commit()
        print("KB seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "./kb_content")
