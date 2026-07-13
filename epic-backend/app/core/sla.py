"""
SLA (Service Level Agreement) policy.

Centralizes the resolution-time targets per priority so ticket creation, priority
changes, and dashboard reporting all agree on the same numbers. Hours are wall-clock
hours from ticket creation (v1 — no business-hours calendar yet).

SPEC §4 (business-hours SLA model) — Part 1 of 2
--------------------------------------------------
Everything above this docstring section (`SLA_HOURS_BY_PRIORITY`, `compute_due_at`,
`sla_status`, `AT_RISK_THRESHOLD`) is the pre-existing 24/7 wall-clock engine. It is
UNTOUCHED and still the one actually consumed by `tickets/service.py` and
`core/sla_scanner.py` today.

Everything below is a NEW, STANDALONE business-hours SLA engine for SPEC §4. Per this
session's explicit scope, it is NOT wired into ticket creation, status changes, or
`sla_scanner.py` yet — that wiring is Part 2 (see /PROGRESS.md). This part only has to be
correct and independently testable: given a location's IANA timezone, a ticket_type, a
priority, and a start timestamp, compute the Response/Resolution SLA due timestamps and
the business-hours elapsed between two timestamps.

Business-hours calendar (SPEC §4/§10): Monday-Friday, 09:00-18:00 *local* time in the
ticket's location timezone, no holiday calendar (explicitly out of scope per SPEC §10).

Timezone handling: uses the stdlib `zoneinfo` (PEP 615) rather than `pytz` — no new
runtime dependency beyond the `tzdata` package (added to pyproject.toml) needed for
environments without a system IANA tz database. `zoneinfo`-backed datetimes recompute
their UTC offset per-instant, so constructing each business day's 09:00/18:00 window
directly against that calendar date (rather than adding `timedelta`s across days) is
what makes the DST-transition day arithmetic correct "for free" — see `_business_window`.

Two assumptions made explicit here (also logged in /PROGRESS.md's §4 session note,
since the spec text left them ambiguous rather than this being a silent guess):

1. **Priority naming.** SPEC §4's matrix is written as P1-P4, but every existing
   priority column/enum in this codebase (`tickets/models.py: PRIORITIES`, this file's
   own `SLA_HOURS_BY_PRIORITY`) uses CRITICAL/HIGH/MEDIUM/LOW. Assumed mapping, ordered
   by urgency to match: CRITICAL=P1, HIGH=P2, MEDIUM=P3, LOW=P4. If product intends a
   different mapping (e.g. a ticket could be MEDIUM priority but P1-tier for a VIP
   location), `BUSINESS_HOURS_SLA_PRIORITY_LEVELS` below is the one dict to change.
2. **ticket_type does NOT currently change the targets.** SPEC §4 says targets are
   "keyed by (ticket_type × priority)" but the matrix it then gives (P1: 15min/2hr, P2:
   30min/4hr, P3: 60min/24hr, P4: 120min/48hr) only varies by priority — no
   ticket_type-specific numbers are given anywhere in SPEC.md, and PROGRESS.md's §4 row
   independently confirms today's (24/7) engine is likewise "keyed by priority only (not
   ticket_type x priority)". Rather than inventing per-type multipliers with no spec
   basis, `get_business_hours_sla_targets()` below still takes and validates
   `ticket_type` (so the call signature already matches what §4 asks for and Part 2 can
   wire it in unchanged), but every ticket_type currently maps to the same priority-only
   matrix. `BUSINESS_HOURS_SLA_TARGETS` is deliberately the single place to add
   per-ticket_type variation later if product clarifies this.
"""
from datetime import datetime, timedelta, timezone as _dt_timezone
from zoneinfo import ZoneInfo

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


# ═══════════════════════════════════════════════════════════════════════════════════
# SPEC §4 — business-hours SLA engine (Part 1 of 2). NOT wired into any service/router
# code yet — see the module docstring above and /PROGRESS.md for what "Part 1" covers.
# ═══════════════════════════════════════════════════════════════════════════════════

# Business calendar (SPEC §4/§10): Mon-Fri 09:00-18:00 *local* time, no holidays.
BUSINESS_HOURS_START = 9   # 09:00 local, inclusive
BUSINESS_HOURS_END = 18    # 18:00 local, exclusive
BUSINESS_WEEKDAYS = {0, 1, 2, 3, 4}  # Python date.weekday(): Monday=0 ... Sunday=6

# Assumption #1 (see module docstring): maps this codebase's existing priority values
# to SPEC §4's P1-P4 naming, ordered by urgency.
BUSINESS_HOURS_SLA_PRIORITY_LEVELS = {
    "CRITICAL": "P1",
    "HIGH": "P2",
    "MEDIUM": "P3",
    "LOW": "P4",
}

# SPEC §4 target matrix, converted to minutes for both clocks.
# P1: 15min/2hr, P2: 30min/4hr, P3: 60min/24hr, P4: 120min/48hr.
BUSINESS_HOURS_SLA_TARGETS = {
    "P1": {"response_minutes": 15, "resolution_minutes": 2 * 60},
    "P2": {"response_minutes": 30, "resolution_minutes": 4 * 60},
    "P3": {"response_minutes": 60, "resolution_minutes": 24 * 60},
    "P4": {"response_minutes": 120, "resolution_minutes": 48 * 60},
}

# Mirrors app.modules.tickets.models.TICKET_TYPES. Duplicated as a local tuple (rather
# than imported) because tickets/models.py already imports from this module
# (`from ...core.sla import sla_status`) — importing back from tickets/models.py here
# would create a circular import. Keep in sync if TICKET_TYPES ever changes.
BUSINESS_HOURS_SLA_TICKET_TYPES = ("INCIDENT", "SERVICE_REQUEST", "PROBLEM", "CHANGE_REQUEST")


def get_business_hours_sla_targets(ticket_type: str, priority: str) -> dict:
    """
    Returns {"response_minutes": int, "resolution_minutes": int} for the given
    ticket_type + priority, per SPEC §4's target matrix.

    Raises ValueError on an unrecognized ticket_type or priority (fail closed, SPEC §9
    — this engine has no caller yet, but when Part 2 wires it in, a silently-wrong
    default SLA target would be worse than an explicit error).
    """
    if ticket_type not in BUSINESS_HOURS_SLA_TICKET_TYPES:
        raise ValueError(f"Unknown ticket_type: {ticket_type!r}")
    level = BUSINESS_HOURS_SLA_PRIORITY_LEVELS.get(priority)
    if level is None:
        raise ValueError(f"Unknown priority: {priority!r}")
    # ticket_type is validated but does not (yet) change the result — see assumption #2
    # in the module docstring.
    return dict(BUSINESS_HOURS_SLA_TARGETS[level])


def resolve_location_timezone(location) -> str:
    """
    Duck-typed accessor for a Location-like object's IANA timezone name (SPEC §4).
    Deliberately does not import app.modules.catalogue.models.Location — this module is
    meant to stay a dependency-free, standalone calculation engine this session; Part 2
    can call this with a real `Location` instance (which already has a `.timezone`
    column, added in the §1/§2 session) or any object exposing a `.timezone` attribute.
    """
    tz_name = getattr(location, "timezone", None)
    if not tz_name:
        raise ValueError("location has no timezone set")
    return tz_name


def _business_window(d, tz: ZoneInfo):
    """
    Returns (window_start, window_end) as tz-aware datetimes for calendar date `d` in
    timezone `tz`, or None if `d` is not a business day (SPEC §10: no holiday calendar,
    so "not a business day" only ever means Saturday/Sunday).

    Constructing the window directly against date `d` (rather than adding a `timedelta`
    to some earlier point) is what makes this correct across a DST transition: zoneinfo
    resolves the correct UTC offset for *this specific* local wall-clock date/time,
    independent of what the offset was on any other day.
    """
    if d.weekday() not in BUSINESS_WEEKDAYS:
        return None
    start = datetime(d.year, d.month, d.day, BUSINESS_HOURS_START, 0, tzinfo=tz)
    end = datetime(d.year, d.month, d.day, BUSINESS_HOURS_END, 0, tzinfo=tz)
    return start, end


def _next_business_moment(point: datetime, tz: ZoneInfo) -> datetime:
    """
    Given a tz-aware `point` (already in `tz`), returns the next moment >= `point` that
    lies within a business-hours window: `point` unchanged if it's already inside one,
    the same day's 09:00 if `point` is before it, or the next business day's 09:00
    otherwise (skipping weekends).
    """
    d = point.date()
    while True:
        window = _business_window(d, tz)
        if window is not None:
            start, end = window
            if point < start:
                return start
            if point < end:
                return point
        d = d + timedelta(days=1)
        point = datetime(d.year, d.month, d.day, 0, 0, tzinfo=tz)


def business_hours_elapsed(start: datetime, end: datetime, timezone_name: str) -> timedelta:
    """
    Business-hours elapsed between two naive-UTC datetimes (matching the convention
    every DateTime column/value in this codebase uses — see core/time.py's docstring),
    measured against `timezone_name`'s Mon-Fri 09:00-18:00 local calendar (SPEC §4/§10).

    Used later (Part 2) for "time remaining" calculations — e.g. remaining business
    minutes = target_minutes - business_hours_elapsed(created_at, utcnow(), tz).

    Returns timedelta(0) if `end <= start`. Any time outside business hours (evenings,
    nights, weekends) contributes nothing, whichever side of the window it falls on.
    """
    if end <= start:
        return timedelta(0)
    tz = ZoneInfo(timezone_name)
    start_local = start.replace(tzinfo=_dt_timezone.utc).astimezone(tz)
    end_local = end.replace(tzinfo=_dt_timezone.utc).astimezone(tz)

    total = timedelta(0)
    d = start_local.date()
    while d <= end_local.date():
        window = _business_window(d, tz)
        if window is not None:
            w_start, w_end = window
            overlap_start = max(w_start, start_local)
            overlap_end = min(w_end, end_local)
            if overlap_end > overlap_start:
                total += overlap_end - overlap_start
        d += timedelta(days=1)
    return total


def add_business_minutes(start: datetime, minutes: float, timezone_name: str) -> datetime:
    """
    Adds `minutes` of business time (Mon-Fri 09:00-18:00 local, SPEC §4/§10) to a
    naive-UTC `start` datetime, in the given IANA timezone (`timezone_name`), returning a
    naive-UTC datetime — the same convention `core/time.utcnow()` uses for every
    DateTime column in this codebase, so the result can later be assigned directly to a
    column like `Ticket.sla_due_at` without any further conversion.

    If `start` falls outside business hours (evenings, nights, weekends), the clock only
    starts running from the next business-hours opening — e.g. a ticket created at 20:00
    Tuesday has its clock start at 09:00 Wednesday.

    Raises ValueError if `minutes` is negative.
    """
    if minutes < 0:
        raise ValueError("minutes must be >= 0")
    tz = ZoneInfo(timezone_name)
    point = start.replace(tzinfo=_dt_timezone.utc).astimezone(tz)
    point = _next_business_moment(point, tz)
    remaining = timedelta(minutes=minutes)

    while True:
        d = point.date()
        _, w_end = _business_window(d, tz)  # point is always inside a valid window here
        capacity = w_end - point
        if remaining <= capacity:
            result = point + remaining
            return result.astimezone(_dt_timezone.utc).replace(tzinfo=None)
        remaining -= capacity
        next_day = d + timedelta(days=1)
        point = _next_business_moment(
            datetime(next_day.year, next_day.month, next_day.day, 0, 0, tzinfo=tz), tz
        )


def compute_business_hours_sla_due_dates(
    *, ticket_type: str, priority: str, start: datetime, timezone_name: str
) -> dict:
    """
    SPEC §4 entry point (Part 1 of 2 — standalone engine only; NOT wired into ticket
    creation/status-change flows yet, see /PROGRESS.md).

    Given a ticket_type, priority, a business-hours start timestamp (naive UTC, e.g.
    `Ticket.created_at`) and an IANA timezone name (e.g. `location.timezone`), returns
    the Response and Resolution SLA due timestamps, both naive UTC:

        {"response_due_at": datetime, "resolution_due_at": datetime}

    Both due dates are computed independently from the same `start` (matching SPEC §4's
    "Independent Response + Resolution clocks").
    """
    targets = get_business_hours_sla_targets(ticket_type, priority)
    return {
        "response_due_at": add_business_minutes(start, targets["response_minutes"], timezone_name),
        "resolution_due_at": add_business_minutes(start, targets["resolution_minutes"], timezone_name),
    }