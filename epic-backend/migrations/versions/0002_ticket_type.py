"""Add ticket_type classification (Incident / Service Request / Problem / Change Request).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tickets",
        sa.Column("ticket_type", sa.String(24), nullable=False, server_default="INCIDENT"),
    )
    op.create_index("ix_tickets_ticket_type", "tickets", ["ticket_type"])


def downgrade():
    op.drop_index("ix_tickets_ticket_type", table_name="tickets")
    op.drop_column("tickets", "ticket_type")