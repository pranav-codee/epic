"""Allow ticket_audit_logs.ticket_id to be NULL so the audit log can also record
system/security events with no associated ticket (role grants/revocations, forced
session revocation, logins/failed logins) — closes the A09 Security Logging &
Monitoring Failure gap.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    # batch_alter_table is required for SQLite (which can't ALTER COLUMN in place);
    # it also works transparently against the on-prem MS SQL Server target.
    with op.batch_alter_table("ticket_audit_logs") as batch_op:
        batch_op.alter_column(
            "ticket_id",
            existing_type=sa.String(36),
            nullable=True,
        )
        batch_op.create_index("ix_audit_actor_action", ["actor_id", "action"])
        batch_op.create_index("ix_audit_action_created", ["action", "created_at"])


def downgrade():
    with op.batch_alter_table("ticket_audit_logs") as batch_op:
        batch_op.drop_index("ix_audit_action_created")
        batch_op.drop_index("ix_audit_actor_action")
        batch_op.alter_column(
            "ticket_id",
            existing_type=sa.String(36),
            nullable=False,
        )