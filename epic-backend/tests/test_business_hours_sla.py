"""
Unit tests for the SPEC §4 business-hours SLA engine (app/core/sla.py — the new
functions below `sla_status()`; the pre-existing 24/7 wall-clock engine above it is
untouched and unaffected by this file).

Covers, per this session's scope:
  - a mid-week same-day window
  - a window that spans a weekend
  - a window that spans a DST transition (Europe/Warsaw)
  - a window starting outside business hours

All start/end datetimes below are naive UTC, matching every other datetime value in
this codebase (see app/core/time.py's docstring) — the same convention
`add_business_minutes`/`business_hours_elapsed` accept and return.
"""
from datetime import datetime, timedelta

import pytest

from app.core.sla import (
    add_business_minutes,
    business_hours_elapsed,
    compute_business_hours_sla_due_dates,
    get_business_hours_sla_targets,
    resolve_location_timezone,
    BUSINESS_HOURS_SLA_TARGETS,
    BUSINESS_HOURS_SLA_PRIORITY_LEVELS,
)


# ─────────────────────────────────────────────────────────────────────────────────
# Target matrix / lookup
# ─────────────────────────────────────────────────────────────────────────────────

def test_target_matrix_matches_spec_section_4():
    assert BUSINESS_HOURS_SLA_TARGETS["P1"] == {"response_minutes": 15, "resolution_minutes": 120}
    assert BUSINESS_HOURS_SLA_TARGETS["P2"] == {"response_minutes": 30, "resolution_minutes": 240}
    assert BUSINESS_HOURS_SLA_TARGETS["P3"] == {"response_minutes": 60, "resolution_minutes": 1440}
    assert BUSINESS_HOURS_SLA_TARGETS["P4"] == {"response_minutes": 120, "resolution_minutes": 2880}


def test_priority_mapping_assumption_is_explicit():
    # Assumption #1 (see app/core/sla.py module docstring): existing CRITICAL/HIGH/
    # MEDIUM/LOW priorities map onto SPEC §4's P1-P4 in urgency order.
    assert BUSINESS_HOURS_SLA_PRIORITY_LEVELS == {
        "CRITICAL": "P1", "HIGH": "P2", "MEDIUM": "P3", "LOW": "P4",
    }


def test_get_business_hours_sla_targets_for_every_priority():
    assert get_business_hours_sla_targets("INCIDENT", "CRITICAL") == {"response_minutes": 15, "resolution_minutes": 120}
    assert get_business_hours_sla_targets("INCIDENT", "HIGH") == {"response_minutes": 30, "resolution_minutes": 240}
    assert get_business_hours_sla_targets("INCIDENT", "MEDIUM") == {"response_minutes": 60, "resolution_minutes": 1440}
    assert get_business_hours_sla_targets("INCIDENT", "LOW") == {"response_minutes": 120, "resolution_minutes": 2880}


def test_targets_identical_across_ticket_types_per_assumption_2():
    # Assumption #2: spec gives no per-ticket_type numbers, so all four ticket types
    # currently resolve to the same priority-only matrix.
    for ticket_type in ("INCIDENT", "SERVICE_REQUEST", "PROBLEM", "CHANGE_REQUEST"):
        assert get_business_hours_sla_targets(ticket_type, "HIGH") == {"response_minutes": 30, "resolution_minutes": 240}


def test_unknown_ticket_type_or_priority_raises_value_error():
    with pytest.raises(ValueError):
        get_business_hours_sla_targets("NOT_A_TYPE", "HIGH")
    with pytest.raises(ValueError):
        get_business_hours_sla_targets("INCIDENT", "NOT_A_PRIORITY")


def test_resolve_location_timezone_duck_typing():
    class FakeLocation:
        timezone = "Asia/Kolkata"

    assert resolve_location_timezone(FakeLocation()) == "Asia/Kolkata"

    class NoTimezone:
        timezone = None

    with pytest.raises(ValueError):
        resolve_location_timezone(NoTimezone())


# ─────────────────────────────────────────────────────────────────────────────────
# Mid-week, same-day window (Asia/Kolkata, no DST, simplest case)
# ─────────────────────────────────────────────────────────────────────────────────

def test_mid_week_same_day_add_business_minutes():
    # Wednesday 2026-07-15, 10:00 IST == 04:30 UTC.
    start = datetime(2026, 7, 15, 4, 30, 0)
    due = add_business_minutes(start, 15, "Asia/Kolkata")  # P1 response target
    # 10:00 + 15min IST == 10:15 IST == 04:45 UTC
    assert due == datetime(2026, 7, 15, 4, 45, 0)


def test_mid_week_same_day_elapsed_is_wall_clock_when_fully_inside_window():
    start = datetime(2026, 7, 15, 4, 30, 0)   # 10:00 IST
    end = datetime(2026, 7, 15, 6, 30, 0)     # 12:00 IST
    assert business_hours_elapsed(start, end, "Asia/Kolkata") == timedelta(hours=2)


def test_mid_week_response_and_resolution_due_dates_independent():
    start = datetime(2026, 7, 15, 4, 30, 0)  # Wed 10:00 IST
    result = compute_business_hours_sla_due_dates(
        ticket_type="INCIDENT", priority="CRITICAL", start=start, timezone_name="Asia/Kolkata",
    )
    assert result["response_due_at"] == datetime(2026, 7, 15, 4, 45, 0)      # +15 min
    assert result["resolution_due_at"] == datetime(2026, 7, 15, 6, 30, 0)    # +2h business


# ─────────────────────────────────────────────────────────────────────────────────
# Window spanning a weekend
# ─────────────────────────────────────────────────────────────────────────────────

def test_window_spanning_weekend_add_business_minutes():
    # Friday 2026-07-17, 17:00 IST == 11:30 UTC. Only 1h (60min) of business time left
    # before the 18:00 close, so adding 120min (P1 resolution) must roll over Sat/Sun
    # to Monday 2026-07-20, using the remaining 60min from 09:00 IST -> 10:00 IST.
    start = datetime(2026, 7, 17, 11, 30, 0)
    due = add_business_minutes(start, 120, "Asia/Kolkata")
    assert due == datetime(2026, 7, 20, 4, 30, 0)  # Monday 10:00 IST == 04:30 UTC


def test_window_spanning_weekend_elapsed_only_counts_business_time():
    start = datetime(2026, 7, 17, 11, 30, 0)   # Fri 17:00 IST
    end = datetime(2026, 7, 20, 4, 30, 0)      # Mon 10:00 IST
    # Fri 17:00-18:00 (1h) + Sat/Sun (0h, weekend) + Mon 09:00-10:00 (1h) == 2h,
    # regardless of the ~65 wall-clock hours between start and end.
    assert business_hours_elapsed(start, end, "Asia/Kolkata") == timedelta(hours=2)


def test_weekend_add_then_elapsed_round_trip_matches_target_minutes():
    # add_business_minutes and business_hours_elapsed are inverses: elapsed business
    # time between a start and its computed due date must equal the minutes added.
    start = datetime(2026, 7, 17, 11, 30, 0)  # Fri 17:00 IST
    for minutes in (15, 30, 60, 120, 240, 1440, 2880):
        due = add_business_minutes(start, minutes, "Asia/Kolkata")
        elapsed = business_hours_elapsed(start, due, "Asia/Kolkata")
        assert elapsed == timedelta(minutes=minutes), f"mismatch for {minutes} minutes"


# ─────────────────────────────────────────────────────────────────────────────────
# Window spanning a DST transition (Europe/Warsaw — EU clocks forward the last Sunday
# of March; 2026-03-29 is that Sunday, so a Friday->Monday window crosses it. As with
# every EU DST rule, the transition itself falls on a Sunday, i.e. a weekend day the
# business calendar already skips — the point of this test is that the multi-day
# roll-forward and Monday's window are still computed with the *correct* (post-
# transition) UTC offset, not the Friday one.)
# ─────────────────────────────────────────────────────────────────────────────────

def test_dst_transition_offset_actually_changes_between_friday_and_monday():
    # Sanity-check the fixture itself: Warsaw is UTC+1 (CET) on Friday 2026-03-27 and
    # UTC+2 (CEST) on Monday 2026-03-30 — i.e. the transition genuinely falls inside
    # this window, so the test below is actually exercising DST-crossing arithmetic.
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Warsaw")
    friday_offset = datetime(2026, 3, 27, 9, 0, tzinfo=tz).utcoffset()
    monday_offset = datetime(2026, 3, 30, 9, 0, tzinfo=tz).utcoffset()
    assert friday_offset == timedelta(hours=1)
    assert monday_offset == timedelta(hours=2)
    assert friday_offset != monday_offset


def test_dst_transition_add_business_minutes():
    # Friday 2026-03-27, 16:00 CET == 15:00 UTC. Business capacity left Friday: 2h
    # (16:00-18:00). Add 600min (10h): 480min remain after Friday, rolling to Monday
    # 2026-03-30 (Sat/Sun/the-DST-Sunday all skipped as non-business days), starting at
    # Monday's 09:00 *CEST* (already post-transition) -> 09:00 + 480min = 17:00 CEST.
    start = datetime(2026, 3, 27, 15, 0, 0)
    due = add_business_minutes(start, 600, "Europe/Warsaw")
    # Monday 2026-03-30 17:00 CEST (UTC+2) == 15:00 UTC.
    assert due == datetime(2026, 3, 30, 15, 0, 0)


def test_dst_transition_elapsed_round_trip_matches_target_minutes():
    start = datetime(2026, 3, 27, 15, 0, 0)  # Fri 16:00 CET
    for minutes in (15, 30, 60, 120, 240, 1440, 2880):
        due = add_business_minutes(start, minutes, "Europe/Warsaw")
        elapsed = business_hours_elapsed(start, due, "Europe/Warsaw")
        assert elapsed == timedelta(minutes=minutes), f"mismatch for {minutes} minutes across DST"


def test_dst_transition_elapsed_between_friday_and_monday_windows():
    # Full Friday window (9h) + full Monday window (9h) == 18h business time, spanning
    # the DST jump, with nothing double-counted or dropped because of the 1-hour shift.
    start = datetime(2026, 3, 27, 8, 0, 0)   # Fri 09:00 CET == 08:00 UTC
    end = datetime(2026, 3, 30, 16, 0, 0)    # Mon 18:00 CEST == 16:00 UTC
    assert business_hours_elapsed(start, end, "Europe/Warsaw") == timedelta(hours=18)


# ─────────────────────────────────────────────────────────────────────────────────
# Window starting outside business hours (evenings, before-open, weekend)
# ─────────────────────────────────────────────────────────────────────────────────

def test_start_after_hours_snaps_to_next_morning():
    # Tuesday 2026-07-14, 20:00 IST == 14:30 UTC (after the 18:00 close).
    start = datetime(2026, 7, 14, 14, 30, 0)
    due = add_business_minutes(start, 30, "Asia/Kolkata")
    # Clock only starts at Wednesday 09:00 IST == 03:30 UTC, so due == 09:30 IST.
    assert due == datetime(2026, 7, 15, 4, 0, 0)


def test_start_before_hours_snaps_to_same_morning_open():
    # Wednesday 2026-07-15, 05:00 IST (before the 09:00 open) == Tue 23:30 UTC.
    start = datetime(2026, 7, 14, 23, 30, 0)
    due = add_business_minutes(start, 15, "Asia/Kolkata")
    # Clock starts at 09:00 IST same day, so due == 09:15 IST == 03:45 UTC.
    assert due == datetime(2026, 7, 15, 3, 45, 0)


def test_start_on_weekend_snaps_to_monday():
    # Saturday 2026-07-18, noon IST == 06:30 UTC.
    start = datetime(2026, 7, 18, 6, 30, 0)
    due = add_business_minutes(start, 60, "Asia/Kolkata")
    # Clock starts Monday 2026-07-20 09:00 IST, so due == 10:00 IST == 04:30 UTC.
    assert due == datetime(2026, 7, 20, 4, 30, 0)


def test_elapsed_before_business_hours_open_contributes_nothing():
    start = datetime(2026, 7, 14, 14, 30, 0)  # Tue 20:00 IST (after hours)
    end = datetime(2026, 7, 15, 3, 30, 0)     # Wed 09:00 IST (the very open)
    assert business_hours_elapsed(start, end, "Asia/Kolkata") == timedelta(0)


def test_elapsed_with_end_before_start_is_zero():
    start = datetime(2026, 7, 15, 6, 30, 0)
    end = datetime(2026, 7, 15, 4, 30, 0)
    assert business_hours_elapsed(start, end, "Asia/Kolkata") == timedelta(0)


# ─────────────────────────────────────────────────────────────────────────────────
# Input validation (SPEC §9 — fail closed rather than silently produce a wrong result)
# ─────────────────────────────────────────────────────────────────────────────────

def test_negative_minutes_rejected():
    with pytest.raises(ValueError):
        add_business_minutes(datetime(2026, 7, 15, 4, 30, 0), -5, "Asia/Kolkata")


def test_unknown_timezone_raises():
    from zoneinfo import ZoneInfoNotFoundError
    with pytest.raises(ZoneInfoNotFoundError):
        add_business_minutes(datetime(2026, 7, 15, 4, 30, 0), 15, "Not/A_Real_Zone")