"""
Catalogue module — read-only service functions for this session. Admin CRUD (creating
Locations/AssignmentGroups/catalogue entries at runtime, group membership management) is
scoped to a later session alongside the dynamic permission registry (SPEC §5) — see
/PROGRESS.md. For now the catalogue is populated by scripts/seed_catalogue.py and read via
these list functions.
"""
from sqlalchemy.orm import Session, joinedload
from .models import Location, AssignmentGroup, CatalogueCategory, CatalogueSubcategory, UserAssignmentGroup


def list_locations(db: Session, *, active_only: bool = True) -> list[Location]:
    q = db.query(Location)
    if active_only:
        q = q.filter(Location.is_active.is_(True))
    return q.order_by(Location.name).all()


def list_assignment_groups(db: Session, *, active_only: bool = True) -> list[AssignmentGroup]:
    q = db.query(AssignmentGroup)
    if active_only:
        q = q.filter(AssignmentGroup.is_active.is_(True))
    return q.order_by(AssignmentGroup.name).all()


def list_groups_for_user(db: Session, user_id: str) -> list[AssignmentGroup]:
    """Groups the given user belongs to — used for the queue view (SPEC §2) once ticket
    listing is wired up to filter by group in a later session."""
    rows = (db.query(UserAssignmentGroup)
            .options(joinedload(UserAssignmentGroup.group))
            .filter(UserAssignmentGroup.user_id == user_id).all())
    return [r.group for r in rows]


def list_catalogue_tree(db: Session) -> list[CatalogueCategory]:
    """Full 3-level tree (category -> subcategory -> item), for the frontend's cascading
    select. Small enough dataset (8 towers, a few hundred rows total) to load in one shot
    rather than paginating."""
    return (db.query(CatalogueCategory)
            .options(joinedload(CatalogueCategory.subcategories).joinedload(CatalogueSubcategory.items))
            .filter(CatalogueCategory.is_active.is_(True))
            .order_by(CatalogueCategory.sort_order).all())