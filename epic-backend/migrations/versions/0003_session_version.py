"""Add session_version to user_profiles for immediate session revocation.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-01
"""
import uuid
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_profiles",
        sa.Column("session_version", sa.String(36), nullable=False,
                  server_default=str(uuid.uuid4())),
    )


def downgrade():
    op.drop_column("user_profiles", "session_version")