"""
SLA (Service Level Agreement) policy.

Centralizes the resolution-time targets per priority so ticket creation, priority
changes, and dashboard reporting all agree on the same numbers. Hours are wall-clock
hours from ticket creation (v1 — no business-hours calendar yet).

SPEC §4 (business-hours SLA model) — Part 1 AND Part 2
--------------------------------------------------------
Everything above this docstring section (`SLA_HOURS_BY_PRIORITY`, `compute_due_at`,
`sla_status`, `AT_RISK_THRESHOLD`) is the pre-existing 24/7 wall-clock engine. It remains
UNTOUCHED (still exists, still importable) but as of Part 2 (see below and /PROGRESS.md
Session 4) it is no longer what `tickets/service.py`'s `create_ticket`/`change_priority`
or `core/sla_scanner.py` actually use for SLA due-date/status computation — both now go
through the business-hours engine below. `compute_due_at`/`sla_status` are left in place
only because nothing forced their removal and deleting working code the moment it stops
being the "current" path is unnecessary churn; a future cleanup session can decide whether
anything still legitimately needs the 24/7 semantics.

The section immediately below ("Part 1 of 2") is the STANDALONE business-hours
calculation engine: given a location's IANA timezone, a ticket_type, a priority, and a
start timestamp, compute the Response/Resolution SLA due timestamps and the
business-hours elapsed between two timestamps. It has no knowledge of `Ticket` rows.

Further below that ("Part 2 of 2— wiring helpers") are the functions Part 2 (this
session) added specifically so `tickets/service.py` and `core/sla_scanner.py` can
evaluate MET/BREACHED (for a clock that has already fired) and live AT_RISK/BREACHED/
ON_TRACK (for a clock still ticking) against the due dates the engine above produces,
without either of those modules needing to reimplement business-hours math themselves.

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

# Safety valve: neither function should ever legitimately need to walk more than a
# few years of calendar days. If it does, something upstream handed it a bad
# datetime (e.g. a corrupted due date, a caller passing years instead of minutes) —
# fail fast with a clear error instead of iterating silently for an unbounded time.
MAX_BUSINESS_HOURS_SPAN_DAYS = 3653  # ~10 years

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
    span_days = (end_local.date() - d).days
    if span_days > MAX_BUSINESS_HOURS_SPAN_DAYS:
        raise ValueError(
            f"business_hours_elapsed span of {span_days} days exceeds the "
            f"{MAX_BUSINESS_HOURS_SPAN_DAYS}-day sanity limit — check start/end inputs"
        )
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

    days_walked = 0
    while True:
        d = point.date()
        _, w_end = _business_window(d, tz)  # point is always inside a valid window here
        capacity = w_end - point
        if remaining <= capacity:
            result = point + remaining
            return result.astimezone(_dt_timezone.utc).replace(tzinfo=None)
        remaining -= capacity
        days_walked += 1
        if days_walked > MAX_BUSINESS_HOURS_SPAN_DAYS:
            raise ValueError(
                f"add_business_minutes exceeded {MAX_BUSINESS_HOURS_SPAN_DAYS} business "
                f"days walking toward {minutes} minutes — check the `minutes` argument"
            )
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


# ═══════════════════════════════════════════════════════════════════════════════════
# SPEC §4 — Part 2 of 2: wiring helpers. Added this session (see /PROGRESS.md Session 4)
# so `tickets/service.py` (creation, first-response, resolution) and
# `core/sla_scanner.py` (live AT_RISK/BREACHED polling) can consume the Part 1 engine
# above without either of those modules needing to reimplement business-hours math
# themselves.
# ═══════════════════════════════════════════════════════════════════════════════════

# Fallback IANA timezone used only when a ticket has no resolvable location (SPEC §1 left
# Ticket.location_id nullable at the DB level — see tickets/models.py's comment — since
# not every existing user has a home_location yet). Matches
# catalogue.models.Location's own column default ("Asia/Kolkata", the HO location's
# zone), so an unset location behaves like the default HQ timezone rather than an
# arbitrary guess.
DEFAULT_SLA_TIMEZONE = "Asia/Kolkata"


def effective_due_at(due_at: datetime | None, paused_seconds: float | int | None = 0) -> datetime | None:
    """
    Shifts a persisted Response/Resolution due timestamp forward by however long the
    ticket has spent paused so far (SPEC §3: "Resolution SLA clock pauses during
    PEND_USER/PEND_3RDPARTY", tracked in `Ticket.sla_paused_total_seconds` since
    Session 2 specifically so a later §4 session could use it — this is that session).

    Deliberately a *plain* wall-clock shift (`due_at + timedelta(seconds=paused_seconds)`),
    not a second business-hours conversion of the paused duration itself: "the clock
    pauses" means that stretch of real time simply doesn't count against the SLA, so the
    due date moves out by exactly the wall-clock duration that was paused. Part 1's module
    docstring (assumption #6) flagged this exact question as unresolved; this is Part 2's
    answer — the simpler, more predictable interpretation, rather than re-running
    business-hours math on the pause window itself (which could itself span
    weekends/evenings and compound in confusing ways). See /PROGRESS.md Session 4 for the
    full reasoning, including why this only applies to the Resolution clock in practice
    today (no code path currently pauses before a first response).

    Returns `due_at` unchanged (including None) if there's nothing to shift.
    """
    if due_at is None or not paused_seconds:
        return due_at
    return due_at + timedelta(seconds=paused_seconds)


def business_hours_sla_result(*, due_at: datetime | None, actual_at: datetime) -> str | None:
    """
    MET/BREACHED for a clock that has actually fired — SPEC §4 Part 2's "on first
    response, evaluate response_sla_status" / "on resolution, evaluate
    resolution_sla_status" moment. `due_at` should already have
    `effective_due_at()` applied by the caller if pause time needs to count.

    Returns None (caller should treat this as "cannot evaluate, leave the status field
    alone") if `due_at` is unknown — e.g. a ticket created before this session's
    `response_due_at`/`resolution_due_at` columns existed.
    """
    if due_at is None:
        return None
    return "MET" if actual_at <= due_at else "BREACHED"


def business_hours_live_status(*, due_at: datetime | None, created_at: datetime, timezone_name: str,
                                target_minutes: float, now: datetime | None = None,
                                paused_seconds: float | int | None = 0) -> str:
    """
    Live AT_RISK/BREACHED/ON_TRACK read for a clock that hasn't fired yet — what
    `core/sla_scanner.py` polls on a timer for the Response and Resolution clocks
    independently (SPEC §4: "Independent Response + Resolution clocks"). Business-hours
    -aware replacement for the pre-existing wall-clock `sla_status()` above, used only for
    the "still ticking" case — a clock that has already fired is evaluated once, directly,
    via `business_hours_sla_result()` above, never through this function.

    Returns "NONE" if `due_at` is unknown.
    """
    if due_at is None:
        return "NONE"
    now = now or utcnow()
    eff_due = effective_due_at(due_at, paused_seconds)
    if now > eff_due:
        return "BREACHED"
    elapsed_minutes = business_hours_elapsed(created_at, now, timezone_name).total_seconds() / 60.0
    remaining_minutes = target_minutes - elapsed_minutes
    if target_minutes > 0 and (remaining_minutes / target_minutes) <= AT_RISK_THRESHOLD:
        return "AT_RISK"
    return "ON_TRACK"