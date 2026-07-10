"""
SLA (Service Level Agreement) policy.

Centralizes the resolution-time targets per priority so ticket creation, priority
changes, and dashboard reporting all agree on the same numbers. Hours are wall-clock
hours from ticket creation (v1 — no business-hours calendar yet).
"""
from datetime import datetime, timedelta

from .time import utcnow

# Resolution-time targets, in hours, per priority. Tune freely — every consumer
# (ticket service + dashboard reporting) reads from this single source of truth.
SLA_HOURS_BY_PRIORITY = {
    "CRITICAL": 4,
    "HIGH": 8,
    "MEDIUM": 24,
    "LOW": 72,
}

# A ticket is flagged AT_RISK once less than this fraction of its total SLA window
# remains (and it isn't breached yet). E.g. 0.2 == "less than 20% of the clock left".
AT_RISK_THRESHOLD = 0.2


def compute_due_at(priority: str, from_time: datetime | None = None) -> datetime:
    base = from_time or utcnow()
    hours = SLA_HOURS_BY_PRIORITY.get(priority, SLA_HOURS_BY_PRIORITY["MEDIUM"])
    return base + timedelta(hours=hours)


def sla_status(*, priority: str, created_at: datetime, sla_due_at: datetime | None,
                resolved_at: datetime | None, closed_at: datetime | None,
                now: datetime | None = None) -> str:
    """Returns one of: NONE, MET, BREACHED, AT_RISK, ON_TRACK."""
    if sla_due_at is None:
        return "NONE"
    now = now or utcnow()
    end = resolved_at or closed_at
    if end is not None:
        return "MET" if end <= sla_due_at else "BREACHED"
    if now > sla_due_at:
        return "BREACHED"
    total_window = (sla_due_at - created_at).total_seconds()
    remaining = (sla_due_at - now).total_seconds()
    if total_window > 0 and (remaining / total_window) <= AT_RISK_THRESHOLD:
        return "AT_RISK"
    return "ON_TRACK"