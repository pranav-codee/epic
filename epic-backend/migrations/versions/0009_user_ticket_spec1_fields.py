"""add user home_location/user_type + ticket SPEC §1 fields (location, catalogue hierarchy,
channel, device fields, requestor, assignment_group, first_response_at, sla status fields,
breached_reason, vendor_ticket_id, is_from_email_mgr)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    # --- user_profiles ---
    op.add_column("user_profiles", sa.Column("user_type", sa.String(16), nullable=False, server_default="INTERNAL"))
    op.add_column("user_profiles", sa.Column("home_location_id", sa.String(36), sa.ForeignKey("locations.id")))
    op.create_index("ix_user_profiles_home_location_id", "user_profiles", ["home_location_id"])

    # --- tickets ---
    op.add_column("tickets", sa.Column("requestor_id", sa.String(36), sa.ForeignKey("user_profiles.id")))
    op.add_column("tickets", sa.Column("location_id", sa.String(36), sa.ForeignKey("locations.id")))
    op.add_column("tickets", sa.Column("category_id", sa.String(36), sa.ForeignKey("catalogue_categories.id")))
    op.add_column("tickets", sa.Column("subcategory_id", sa.String(36), sa.ForeignKey("catalogue_subcategories.id")))
    op.add_column("tickets", sa.Column("item_id", sa.String(36), sa.ForeignKey("catalogue_items.id")))
    op.add_column("tickets", sa.Column("channel", sa.String(24), nullable=False, server_default="SELF_SERVICE"))
    op.add_column("tickets", sa.Column("device_name", sa.String(256)))
    op.add_column("tickets", sa.Column("device_ip_address", sa.String(64)))
    op.add_column("tickets", sa.Column("device_site_name", sa.String(256)))
    op.add_column("tickets", sa.Column("assignment_group_id", sa.String(36), sa.ForeignKey("assignment_groups.id")))
    op.add_column("tickets", sa.Column("first_response_at", sa.DateTime))
    op.add_column("tickets", sa.Column("response_sla_status", sa.String(16)))
    op.add_column("tickets", sa.Column("resolution_sla_status", sa.String(16)))
    op.add_column("tickets", sa.Column("breached_reason", sa.Text))
    op.add_column("tickets", sa.Column("vendor_ticket_id", sa.String(64)))
    op.add_column("tickets", sa.Column("is_from_email_mgr", sa.Boolean))

    op.create_index("ix_tickets_requestor_id", "tickets", ["requestor_id"])
    op.create_index("ix_tickets_location", "tickets", ["location_id"])
    op.create_index("ix_tickets_category_id", "tickets", ["category_id"])
    op.create_index("ix_tickets_subcategory_id", "tickets", ["subcategory_id"])
    op.create_index("ix_tickets_item_id", "tickets", ["item_id"])
    op.create_index("ix_tickets_assignment_group", "tickets", ["assignment_group_id", "status"])


def downgrade():
    op.drop_index("ix_tickets_assignment_group", table_name="tickets")
    op.drop_index("ix_tickets_item_id", table_name="tickets")
    op.drop_index("ix_tickets_subcategory_id", table_name="tickets")
    op.drop_index("ix_tickets_category_id", table_name="tickets")
    op.drop_index("ix_tickets_location", table_name="tickets")
    op.drop_index("ix_tickets_requestor_id", table_name="tickets")

    op.drop_column("tickets", "is_from_email_mgr")
    op.drop_column("tickets", "vendor_ticket_id")
    op.drop_column("tickets", "breached_reason")
    op.drop_column("tickets", "resolution_sla_status")
    op.drop_column("tickets", "response_sla_status")
    op.drop_column("tickets", "first_response_at")
    op.drop_column("tickets", "assignment_group_id")
    op.drop_column("tickets", "device_site_name")
    op.drop_column("tickets", "device_ip_address")
    op.drop_column("tickets", "device_name")
    op.drop_column("tickets", "channel")
    op.drop_column("tickets", "item_id")
    op.drop_column("tickets", "subcategory_id")
    op.drop_column("tickets", "category_id")
    op.drop_column("tickets", "location_id")
    op.drop_column("tickets", "requestor_id")

    op.drop_index("ix_user_profiles_home_location_id", table_name="user_profiles")
    op.drop_column("user_profiles", "home_location_id")
    op.drop_column("user_profiles", "user_type")