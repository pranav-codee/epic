"""add catalogue tables: locations, assignment_groups, user_assignment_groups,
catalogue_categories/subcategories/items

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "locations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(64)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "assignment_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("is_location_bound", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("location_id", sa.String(36), sa.ForeignKey("locations.id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "user_assignment_groups",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("user_profiles.id"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("assignment_groups.id"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "group_id", name="pk_user_assignment_group"),
    )
    op.create_index("ix_uag_group", "user_assignment_groups", ["group_id"])

    op.create_table(
        "catalogue_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(48), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "catalogue_subcategories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("catalogue_categories.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("category_id", "code", name="uq_subcategory_code_per_category"),
    )
    op.create_index("ix_catalogue_subcategories_category_id", "catalogue_subcategories", ["category_id"])

    op.create_table(
        "catalogue_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subcategory_id", sa.String(36), sa.ForeignKey("catalogue_subcategories.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("subcategory_id", "code", name="uq_item_code_per_subcategory"),
    )
    op.create_index("ix_catalogue_items_subcategory_id", "catalogue_items", ["subcategory_id"])


def downgrade():
    op.drop_table("catalogue_items")
    op.drop_table("catalogue_subcategories")
    op.drop_table("catalogue_categories")
    op.drop_table("user_assignment_groups")
    op.drop_table("assignment_groups")
    op.drop_table("locations")