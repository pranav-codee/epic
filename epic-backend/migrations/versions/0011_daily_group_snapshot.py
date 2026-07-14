"""add daily_group_snapshots table (Production View A: Daily Ops Summary backlog history)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_group_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("assignment_group_id", sa.String(36), sa.ForeignKey("assignment_groups.id"), nullable=True),
        sa.Column("open_incidents_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("open_srs_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("snapshot_date", "assignment_group_id", name="uq_daily_snapshot_date_group"),
    )
    op.create_index(
        "ix_daily_snapshot_date_group", "daily_group_snapshots",
        ["snapshot_date", "assignment_group_id"],
    )
    op.create_index(
        "ix_daily_group_snapshots_snapshot_date", "daily_group_snapshots", ["snapshot_date"],
    )
    op.create_index(
        "ix_daily_group_snapshots_assignment_group_id", "daily_group_snapshots", ["assignment_group_id"],
    )


def downgrade():
    op.drop_index("ix_daily_group_snapshots_assignment_group_id", table_name="daily_group_snapshots")
    op.drop_index("ix_daily_group_snapshots_snapshot_date", table_name="daily_group_snapshots")
    op.drop_index("ix_daily_snapshot_date_group", table_name="daily_group_snapshots")
    op.drop_table("daily_group_snapshots")