"""Initial EPIC v1 schema.

Revision ID: 0001
Revises:
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entra_object_id", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(256), nullable=False, unique=True),
        sa.Column("display_name", sa.String(256)),
        sa.Column("department", sa.String(128)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("last_login_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("user_profiles.id"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "role", name="pk_user_role"),
    )

    op.create_table(
        "ticket_counters",
        sa.Column("year", sa.Integer, primary_key=True),
        sa.Column("last_number", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_number", sa.String(24), unique=True, nullable=False),
        sa.Column("creator_id", sa.String(36), sa.ForeignKey("user_profiles.id"), nullable=False),
        sa.Column("assignee_id", sa.String(36), sa.ForeignKey("user_profiles.id")),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("resolved_at", sa.DateTime),
        sa.Column("closed_at", sa.DateTime),
    )
    op.create_index("ix_tickets_creator_status", "tickets", ["creator_id", "status"])
    op.create_index("ix_tickets_assignee_status", "tickets", ["assignee_id", "status"])
    op.create_index("ix_tickets_status_priority", "tickets", ["status", "priority"])
    op.create_index("ix_tickets_category", "tickets", ["category"])

    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("user_profiles.id"), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_ticket_comments_ticket_created", "ticket_comments", ["ticket_id", "created_at"])

    op.create_table(
        "ticket_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("user_profiles.id"), nullable=False),
        sa.Column("file_name", sa.String(256), nullable=False),
        sa.Column("content_type", sa.String(128)),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_uri", sa.String(512), nullable=False),
        sa.Column("uploaded_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "ticket_audit_logs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("user_profiles.id")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("field", sa.String(64)),
        sa.Column("old_value", sa.String(256)),
        sa.Column("new_value", sa.String(256)),
        sa.Column("metadata_json", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_audit_ticket_created", "ticket_audit_logs", ["ticket_id", "created_at"])

    op.create_table(
        "notification_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id")),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("user_profiles.id")),
        sa.Column("channel", sa.String(32), nullable=False, server_default="TEAMS"),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("sent_at", sa.DateTime),
    )

    op.create_table(
        "knowledge_base_articles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("slug", sa.String(256), unique=True, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("category", sa.String(64)),
        sa.Column("tags", sa.String(512)),
        sa.Column("published", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade():
    for t in ["knowledge_base_articles", "notification_records", "ticket_audit_logs",
              "ticket_attachments", "ticket_comments", "tickets", "ticket_counters",
              "user_roles", "user_profiles"]:
        op.drop_table(t)
