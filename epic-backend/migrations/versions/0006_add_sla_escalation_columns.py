"""add sla escalation notified-at columns

Revision ID: xxxx_add_sla_escalation_columns
Revises: <put_previous_revision_id_here>
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("sla_at_risk_notified_at", sa.DateTime(), nullable=True))
    op.add_column("tickets", sa.Column("sla_breached_notified_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("tickets", "sla_breached_notified_at")
    op.drop_column("tickets", "sla_at_risk_notified_at")