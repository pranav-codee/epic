"""
Reporting module — persisted point-in-time state for the reporting aggregations in
reporting/service.py that need history rather than a live query.

DailyGroupSnapshot backs Production View A ("Daily Ops Summary"): its Inflow/Closures
columns are same-day live queries (created today / resolved today), but its "Yesterday's
Backlog" column needs each Assignment Group's open-ticket count as of yesterday — a value
that is impossible to reconstruct from a live query once today's tickets have already
mutated the open-ticket set. Nothing else in the codebase persists a daily snapshot of
open-ticket state, so this is a new table rather than a reuse of an existing one.
"""
import uuid
from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey, Index, UniqueConstraint
from ...database import Base
from ...core.time import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


class DailyGroupSnapshot(Base):
    """One row per (snapshot_date, Assignment Group) capturing that group's open Incident /
    Service Request counts at the moment the snapshot was taken. Written once per day by
    app.core.daily_snapshot_loop's periodic call into reporting/service.py's
    take_daily_snapshot().

    assignment_group_id is nullable — NULL represents the "Unassigned" bucket (tickets with
    no assignment_group_id), the same convention reporting/service.py's
    inflow_resolved_open_by_group() already uses for its "Unassigned" rollup row, so a ticket
    with no group still counts toward some group's backlog instead of being silently dropped
    from the snapshot.
    """
    __tablename__ = "daily_group_snapshots"
    id = Column(String(36), primary_key=True, default=_uuid)
    snapshot_date = Column(Date, nullable=False, index=True)
    assignment_group_id = Column(String(36), ForeignKey("assignment_groups.id"), nullable=True, index=True)
    open_incidents_count = Column(Integer, nullable=False, default=0, server_default="0")
    open_srs_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        # Application-level idempotency (take_daily_snapshot() deletes-then-reinserts a
        # date's rows in one transaction) is what actually prevents duplicates day-to-day;
        # this constraint is a defense-in-depth backstop against a concurrent double-run
        # inserting two rows for the same (date, group) rather than the primary dedup
        # mechanism. Standard SQL unique-constraint semantics treat NULL as distinct from
        # any other NULL, so this does not by itself prevent two NULL-group rows for the
        # same date — take_daily_snapshot()'s single-row-per-date-per-group construction is
        # what guarantees that in practice.
        UniqueConstraint("snapshot_date", "assignment_group_id", name="uq_daily_snapshot_date_group"),
        Index("ix_daily_snapshot_date_group", "snapshot_date", "assignment_group_id"),
    )

    def __repr__(self):
        return f"<DailyGroupSnapshot {self.snapshot_date} group={self.assignment_group_id}>"