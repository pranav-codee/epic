"""
Read-only endpoints for this session — populate the ticket-creation cascading select and the
location/group pickers. Any authenticated user may read these (they're reference data, not
PII), matching the low-sensitivity treatment other reference endpoints (e.g. kb) get
elsewhere in the codebase. Admin write endpoints (create/edit group, edit catalogue) are
later-session work tied to the roles.create_edit / catalogue.edit permissions in SPEC §5.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from . import service
from .schemas import LocationOut, AssignmentGroupOut, CatalogueCategoryOut
from ...database import get_db
from ...dependencies import get_current_user

router = APIRouter()


@router.get("/locations", response_model=list[LocationOut])
def list_locations(db: Session = Depends(get_db), me=Depends(get_current_user)):
    return service.list_locations(db)


@router.get("/assignment-groups", response_model=list[AssignmentGroupOut])
def list_assignment_groups(db: Session = Depends(get_db), me=Depends(get_current_user)):
    return service.list_assignment_groups(db)


@router.get("/assignment-groups/mine", response_model=list[AssignmentGroupOut])
def list_my_assignment_groups(db: Session = Depends(get_db), me=Depends(get_current_user)):
    return service.list_groups_for_user(db, me.id)


@router.get("/tree", response_model=list[CatalogueCategoryOut])
def get_catalogue_tree(db: Session = Depends(get_db), me=Depends(get_current_user)):
    """Full category -> subcategory -> item tree for the ticket-creation cascading select."""
    return service.list_catalogue_tree(db)