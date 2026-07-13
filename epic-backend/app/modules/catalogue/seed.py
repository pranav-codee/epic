"""
Idempotent seed loader for the catalogue module. Safe to run repeatedly (checks for an
existing row by its unique `code`/`name` before inserting) — matches the style of
scripts/seed_demo.py and scripts/seed_kb.py, just invoked as functions so both a standalone
script and (optionally) app startup / tests can call it directly.
"""
from sqlalchemy.orm import Session
from .models import (
    Location, AssignmentGroup, CatalogueCategory, CatalogueSubcategory, CatalogueItem,
)
from .seed_data import LOCATIONS, ASSIGNMENT_GROUPS_REGIONAL, ASSIGNMENT_GROUPS_GLOBAL, CATALOGUE


def seed_locations(db: Session) -> dict[str, Location]:
    by_code: dict[str, Location] = {}
    for code, name, country, timezone in LOCATIONS:
        loc = db.query(Location).filter(Location.code == code).one_or_none()
        if loc is None:
            loc = Location(code=code, name=name, country=country, timezone=timezone)
            db.add(loc)
            db.flush()
        by_code[code] = loc
    db.commit()
    return by_code


def seed_assignment_groups(db: Session, locations_by_code: dict[str, Location] | None = None) -> None:
    locations_by_code = locations_by_code or seed_locations(db)

    # Regional groups — one per region in LOCATIONS (excluding no region), location-bound.
    region_name_to_code = {
        "Poland": "POLAND", "Egypt": "EGYPT", "Mexico": "MEXICO", "China": "CHINA",
        "Germany": "GERMANY", "Philippines": "PHILIPPINES", "Columbia": "COLUMBIA",
        "Vasind": "VASIND", "HO": "HO",
    }
    for group_name in ASSIGNMENT_GROUPS_REGIONAL:
        region = group_name.replace("IT Infra - ", "")
        code = region_name_to_code.get(region)
        loc = locations_by_code.get(code) if code else None
        existing = db.query(AssignmentGroup).filter(AssignmentGroup.name == group_name).one_or_none()
        if existing is None:
            db.add(AssignmentGroup(name=group_name, is_location_bound=True,
                                   location_id=loc.id if loc else None))

    # Global specialist-domain groups — location-independent.
    for group_name in ASSIGNMENT_GROUPS_GLOBAL:
        existing = db.query(AssignmentGroup).filter(AssignmentGroup.name == group_name).one_or_none()
        if existing is None:
            db.add(AssignmentGroup(name=group_name, is_location_bound=False, location_id=None))

    db.commit()


def seed_catalogue(db: Session) -> None:
    for order, (cat_code, cat_data) in enumerate(CATALOGUE.items()):
        category = db.query(CatalogueCategory).filter(CatalogueCategory.code == cat_code).one_or_none()
        if category is None:
            category = CatalogueCategory(code=cat_code, name=cat_data["name"], sort_order=order)
            db.add(category)
            db.flush()

        for sub_code, (sub_name, item_names) in cat_data["subcategories"].items():
            subcategory = (db.query(CatalogueSubcategory)
                           .filter(CatalogueSubcategory.category_id == category.id,
                                   CatalogueSubcategory.code == sub_code)
                           .one_or_none())
            if subcategory is None:
                subcategory = CatalogueSubcategory(category_id=category.id, code=sub_code, name=sub_name)
                db.add(subcategory)
                db.flush()

            for item_name in item_names:
                item_code = item_name.upper().replace(" ", "_").replace("/", "_")
                existing_item = (db.query(CatalogueItem)
                                  .filter(CatalogueItem.subcategory_id == subcategory.id,
                                          CatalogueItem.code == item_code)
                                  .one_or_none())
                if existing_item is None:
                    db.add(CatalogueItem(subcategory_id=subcategory.id, code=item_code, name=item_name))

    db.commit()


def seed_all(db: Session) -> None:
    locations = seed_locations(db)
    seed_assignment_groups(db, locations)
    seed_catalogue(db)