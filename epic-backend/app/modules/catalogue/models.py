"""
Catalogue module — data-model foundations for SPEC.md §1/§2:
  - Location: physical/regional site, drives home_location + ticket location + SLA timezone.
  - AssignmentGroup: first-class, admin-configurable queue that a ticket is routed to.
  - UserAssignmentGroup: many-to-many membership (a user can belong to more than one group).
  - CatalogueCategory / CatalogueSubcategory / CatalogueItem: the real 3-level ticket
    classification hierarchy (Tower -> Service -> Item), replacing the flat CATEGORIES enum
    that lived in tickets/models.py.

Routing rules (SPEC §6), the permission registry (SPEC §5), and full CRUD/admin endpoints for
these entities are later-session work — see /PROGRESS.md. This session only lays the schema
+ read-side foundations plus seed data so ticket creation can start referencing them.
"""
import uuid
from sqlalchemy import (
    Column, String, Boolean, Integer, ForeignKey, PrimaryKeyConstraint, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from ...database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Location(Base):
    """A physical/regional site. Drives UserProfile.home_location, Ticket.location (SPEC §1),
    AssignmentGroup region-binding (SPEC §2), and — in a later session — the business-hours
    SLA calendar's timezone (SPEC §4)."""
    __tablename__ = "locations"
    id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String(32), unique=True, nullable=False, index=True)   # e.g. "HO", "POLAND"
    name = Column(String(128), nullable=False)
    country = Column(String(64), nullable=True)
    # IANA timezone name (e.g. "Asia/Kolkata", "Europe/Warsaw"). Used by the SLA business-hours
    # calendar in a later session; stored now so Location is a complete, reusable reference.
    timezone = Column(String(64), nullable=False, default="Asia/Kolkata", server_default="Asia/Kolkata")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    def __repr__(self):
        return f"<Location {self.code}>"


class AssignmentGroup(Base):
    """First-class, admin-configurable queue (SPEC §2). A ticket belongs to exactly one group;
    a user can belong to one or more groups (see UserAssignmentGroup)."""
    __tablename__ = "assignment_groups"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(128), unique=True, nullable=False, index=True)
    # Region-bound groups (e.g. "IT Infra - Poland") are scoped to one Location; global
    # specialist-domain groups (e.g. "Network", "O365") are location-independent.
    is_location_bound = Column(Boolean, nullable=False, default=False, server_default="0")
    location_id = Column(String(36), ForeignKey("locations.id"), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    location = relationship("Location")

    def __repr__(self):
        return f"<AssignmentGroup {self.name}>"


class UserAssignmentGroup(Base):
    """Many-to-many membership: a user may belong to more than one AssignmentGroup (e.g. a
    regional generalist who also covers O365 specialist tickets)."""
    __tablename__ = "user_assignment_groups"
    user_id = Column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    group_id = Column(String(36), ForeignKey("assignment_groups.id"), nullable=False)

    group = relationship("AssignmentGroup")

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "group_id", name="pk_user_assignment_group"),
        Index("ix_uag_group", "group_id"),
    )


class CatalogueCategory(Base):
    """Level 1 of the ticket classification hierarchy — one of the 8 IT Service Catalogue
    "towers" (Data Center Services, Network, Cyber Security, Helpdesk/FMS, Email,
    Laptop/Desktop, Backup, License Management)."""
    __tablename__ = "catalogue_categories"
    id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String(48), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    subcategories = relationship("CatalogueSubcategory", cascade="all, delete-orphan",
                                  back_populates="category", order_by="CatalogueSubcategory.name")

    def __repr__(self):
        return f"<CatalogueCategory {self.code}>"


class CatalogueSubcategory(Base):
    """Level 2 — a specific service within a tower (SRS: ~15-25 per tower), e.g.
    "Server Provisioning" under Data Center Services."""
    __tablename__ = "catalogue_subcategories"
    id = Column(String(36), primary_key=True, default=_uuid)
    category_id = Column(String(36), ForeignKey("catalogue_categories.id"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(160), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    category = relationship("CatalogueCategory", back_populates="subcategories")
    items = relationship("CatalogueItem", cascade="all, delete-orphan",
                          back_populates="subcategory", order_by="CatalogueItem.name")

    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_subcategory_code_per_category"),
    )

    def __repr__(self):
        return f"<CatalogueSubcategory {self.code}>"


class CatalogueItem(Base):
    """Level 3 — the specific item/request within a subcategory, e.g. "New VM Request" under
    "Server Provisioning". Seeded with a representative starter set per subcategory; the full
    catalogue is expected to grow via the admin catalogue.edit permission (SPEC §5, later
    session) rather than being hand-seeded exhaustively in this migration."""
    __tablename__ = "catalogue_items"
    id = Column(String(36), primary_key=True, default=_uuid)
    subcategory_id = Column(String(36), ForeignKey("catalogue_subcategories.id"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(160), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    subcategory = relationship("CatalogueSubcategory", back_populates="items")

    __table_args__ = (
        UniqueConstraint("subcategory_id", "code", name="uq_item_code_per_subcategory"),
    )

    def __repr__(self):
        return f"<CatalogueItem {self.code}>"