from pydantic import BaseModel
from typing import List, Optional


class LocationOut(BaseModel):
    id: str
    code: str
    name: str
    country: Optional[str] = None
    timezone: str
    is_active: bool

    class Config:
        from_attributes = True


class AssignmentGroupOut(BaseModel):
    id: str
    name: str
    is_location_bound: bool
    location_id: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class CatalogueItemOut(BaseModel):
    id: str
    code: str
    name: str

    class Config:
        from_attributes = True


class CatalogueSubcategoryOut(BaseModel):
    id: str
    code: str
    name: str
    items: List[CatalogueItemOut] = []

    class Config:
        from_attributes = True


class CatalogueCategoryOut(BaseModel):
    id: str
    code: str
    name: str
    subcategories: List[CatalogueSubcategoryOut] = []

    class Config:
        from_attributes = True