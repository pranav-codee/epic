"""Add tickets.sla_due_at — SLA target resolution deadline, used by dashboard SLA
compliance/breach reporting (see app.core.sla).

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Kept in sync with app.core.sla.SLA_HOURS_BY_PRIORITY for the one-off backfill below.
_SLA_HOURS = {"CRITICAL": 4, "HIGH": 8, "MEDIUM": 24, "LOW": 72}


def upgrade():
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("sla_due_at", sa.DateTime(), nullable=True))

    conn = op.get_bind()
    # Backfill existing rows so historical tickets get a due date too, instead of
    # reporting as SLA "NONE" forever.
    dialect = conn.dialect.name
    for priority, hours in _SLA_HOURS.items():
        if dialect == "sqlite":
            stmt = sa.text(
                "UPDATE tickets SET sla_due_at = datetime(created_at, :offset) WHERE priority = :priority"
            )
            params = {"offset": f"+{hours} hours", "priority": priority}
        elif dialect == "postgresql":
            stmt = sa.text(
                "UPDATE tickets SET sla_due_at = created_at + (:hours || ' hours')::interval WHERE priority = :priority"
            )
            params = {"hours": hours, "priority": priority}
        else:
            # MS SQL Server (on-prem target per pyodbc dependency).
            stmt = sa.text(
                "UPDATE tickets SET sla_due_at = DATEADD(hour, :hours, created_at) WHERE priority = :priority"
            )
            params = {"hours": hours, "priority": priority}
        conn.execute(stmt, params)


def downgrade():
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_column("sla_due_at")