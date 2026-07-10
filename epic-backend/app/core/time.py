"""
Single source of truth for "the current time" across the app.

`datetime.utcnow()` is deprecated as of Python 3.12 (removal scheduled for a future
version) in favour of timezone-aware `datetime.now(datetime.UTC)`. We can't just swap
every call site to the aware form, though: every `DateTime` column in this codebase
(see tickets/models.py, users/models.py, notifications/models.py) is a naive
`DateTime` (no `timezone=True`), and SQLite/MS SQL both give back naive datetimes on
read. Comparing a naive value from the DB against a tz-aware value raises
`TypeError: can't compare offset-naive and offset-aware datetimes` — which would break
every SLA comparison, session-expiry check, and audit-log ordering in one shot.

`utcnow()` below gives the same *value* `datetime.utcnow()` always gave (naive,
UTC-based) while going through the non-deprecated `datetime.now(UTC)` API internally.
This is the standard low-risk migration path: fix the deprecation now, defer the
"make every datetime column timezone-aware" migration (a real schema change) to a
separate piece of work.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime, matching every existing DB column."""
    return datetime.now(timezone.utc).replace(tzinfo=None)