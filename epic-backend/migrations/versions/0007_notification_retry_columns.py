"""add notification retry columns

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "notification_records",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "notification_records",
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_notification_records_next_retry_at",
        "notification_records",
        ["next_retry_at"],
    )


def downgrade():
    op.drop_index("ix_notification_records_next_retry_at", table_name="notification_records")
    op.drop_column("notification_records", "next_retry_at")
    op.drop_column("notification_records", "retry_count")
