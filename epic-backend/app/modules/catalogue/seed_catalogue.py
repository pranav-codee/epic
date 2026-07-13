"""Seed Locations, Assignment Groups, and the IT Service Catalogue hierarchy (SPEC §1/§2).
Idempotent — safe to re-run. Usage: python scripts/seed_catalogue.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine
from app import models  # noqa
from app.modules.catalogue.seed import seed_all

Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    seed_all(db)
    print("Catalogue seed complete: locations, assignment groups, IT service catalogue.")
finally:
    db.close()