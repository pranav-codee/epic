"""add ticket SPEC §3 fields (workflow_status, sla_paused_at, sla_paused_total_seconds)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("workflow_status", sa.String(24), nullable=True))
    op.add_column("tickets", sa.Column("sla_paused_at", sa.DateTime))
    op.add_column(
        "tickets",
        sa.Column("sla_paused_total_seconds", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_tickets_workflow_status", "tickets", ["workflow_status"])


def downgrade():
    op.drop_index("ix_tickets_workflow_status", table_name="tickets")
    op.drop_column("tickets", "sla_paused_total_seconds")
    op.drop_column("tickets", "sla_paused_at")
    op.drop_column("tickets", "workflow_status")