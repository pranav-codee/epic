"""
Integration tests for SPEC §4 Part 2 (this session) — wiring the business-hours SLA
engine (app/core/sla.py's Part 1, already unit-tested in test_business_hours_sla.py)
into the actual ticket lifecycle: creation, first response, resolution, breached_reason
enforcement, and the sla_scanner's per-clock business-hours live status.

Covers:
  1. Ticket creation computes response_due_at/resolution_due_at via the business-hours
     engine (not the old 24/7 compute_due_at), using the ticket's location timezone,
     with a documented fallback when there's no location.
  2. change_priority recomputes both due dates and resets both clocks' notification
     columns.
  3. "First response" (this session's definition: first support-staff comment) sets
     first_response_at and evaluates response_sla_status.
  4. A requestor's own comment does NOT count as first response.
  5. Resolution (via change_status AND via change_workflow_status) evaluates
     resolution_sla_status, honoring SPEC §3 pause time via sla_paused_total_seconds.
  6. breached_reason is required server-side whenever either SLA status is set to
     BREACHED — enforced as an app-layer DomainError, not a DB constraint — and the
     whole mutation (comment/status change) is rolled back if it's missing.
  7. app.core.sla.business_hours_live_status (what sla_scanner.py uses) computes
     AT_RISK/BREACHED live status independently per clock.
"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./epic_test_sla_wiring.db")
os.environ.setdefault("AUTH_PROVIDER", "mock")
os.environ.setdefault("TEAMS_NOTIFICATIONS_ENABLED", "false")

from datetime import timedelta

import pytest

from app.database import SessionLocal, Base, engine
from app import models  # noqa: F401 ensures all models are registered
from app.modules.users.service import upsert_from_identity, set_roles, attach_roles
from app.modules.tickets import service as ticket_service
from app.modules.catalogue.models import Location
from app.core.rbac import Role
from app.core.exceptions import DomainError
from app.core.sla import (
    business_hours_live_status, compute_business_hours_sla_due_dates, DEFAULT_SLA_TIMEZONE,
)
from app.core.time import utcnow


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _make_engineer(db, oid="mock-eng-sla@epl.local"):
    u = upsert_from_identity(db, entra_oid=oid, email=oid, display_name="Engineer SLA", department="IT")
    set_roles(db, u.id, [Role.EMPLOYEE.value, Role.IT_ENGINEER.value])
    attach_roles(u, db)
    return u


def _make_employee(db, oid="mock-emp-sla@epl.local"):
    u = upsert_from_identity(db, entra_oid=oid, email=oid, display_name="Employee SLA", department="Sales")
    set_roles(db, u.id, [Role.EMPLOYEE.value])
    attach_roles(u, db)
    return u


def _make_location(db, code="POLAND", timezone="Europe/Warsaw"):
    loc = Location(code=code, name=code.title(), country="PL", timezone=timezone)
    db.add(loc); db.commit(); db.refresh(loc)
    return loc


# ---------- 1. Creation wires the business-hours engine ----------

def test_creation_sets_due_dates_via_business_hours_engine(db_session):
    loc = _make_location(db_session)
    creator = _make_employee(db_session)
    creator.home_location_id = loc.id
    db_session.commit()

    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN down", description="Cannot connect",
        ticket_type="INCIDENT", category="VPN", priority="CRITICAL",
    )

    assert t.response_due_at is not None
    assert t.resolution_due_at is not None
    # Legacy alias stays in sync for reporting/back-compat.
    assert t.sla_due_at == t.resolution_due_at

    expected = compute_business_hours_sla_due_dates(
        ticket_type="INCIDENT", priority="CRITICAL", start=t.created_at, timezone_name="Europe/Warsaw")
    assert t.response_due_at == expected["response_due_at"]
    assert t.resolution_due_at == expected["resolution_due_at"]


def test_creation_falls_back_to_default_timezone_with_no_location(db_session):
    creator = _make_employee(db_session)
    assert creator.home_location_id is None

    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Laptop broken", description="Won't boot",
        ticket_type="INCIDENT", category="HARDWARE", priority="HIGH",
    )

    expected = compute_business_hours_sla_due_dates(
        ticket_type="INCIDENT", priority="HIGH", start=t.created_at, timezone_name=DEFAULT_SLA_TIMEZONE)
    assert t.response_due_at == expected["response_due_at"]
    assert t.resolution_due_at == expected["resolution_due_at"]


def test_change_priority_recomputes_both_due_dates_and_resets_notifications(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Slow VPN", description="Laggy",
        ticket_type="INCIDENT", category="VPN", priority="LOW",
    )
    old_response_due, old_resolution_due = t.response_due_at, t.resolution_due_at

    t.response_sla_at_risk_notified_at = utcnow()
    t.sla_at_risk_notified_at = utcnow()
    db_session.commit()

    updated = ticket_service.change_priority(db_session, ticket_id=t.id, priority="CRITICAL", actor=engineer)

    assert updated.response_due_at != old_response_due
    assert updated.resolution_due_at != old_resolution_due
    assert updated.sla_due_at == updated.resolution_due_at
    assert updated.response_sla_at_risk_notified_at is None
    assert updated.sla_at_risk_notified_at is None


# ---------- 2/3. First response ----------

def test_engineer_comment_sets_first_response_and_evaluates_met(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Printer down", description="Won't print",
        ticket_type="INCIDENT", category="HARDWARE", priority="LOW",  # generous 120-min response window
    )
    assert t.first_response_at is None
    assert t.response_sla_status is None

    ticket_service.add_comment(db_session, ticket_id=t.id, text="Looking into it", actor=engineer)

    refreshed = ticket_service.get_ticket_or_404(db_session, t.id)
    assert refreshed.first_response_at is not None
    assert refreshed.response_sla_status == "MET"


def test_requestor_comment_does_not_count_as_first_response(db_session):
    creator = _make_employee(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Printer down", description="Won't print",
        ticket_type="INCIDENT", category="HARDWARE", priority="LOW",
    )
    ticket_service.add_comment(db_session, ticket_id=t.id, text="Any update?", actor=creator)

    refreshed = ticket_service.get_ticket_or_404(db_session, t.id)
    assert refreshed.first_response_at is None
    assert refreshed.response_sla_status is None


def test_second_engineer_comment_does_not_re_evaluate_first_response(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Printer down", description="Won't print",
        ticket_type="INCIDENT", category="HARDWARE", priority="LOW",
    )
    ticket_service.add_comment(db_session, ticket_id=t.id, text="Looking into it", actor=engineer)
    first_at = ticket_service.get_ticket_or_404(db_session, t.id).first_response_at

    ticket_service.add_comment(db_session, ticket_id=t.id, text="Still on it", actor=engineer)
    refreshed = ticket_service.get_ticket_or_404(db_session, t.id)
    assert refreshed.first_response_at == first_at


def test_late_first_response_is_breached_with_reason(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Server down", description="Prod outage",
        ticket_type="INCIDENT", category="NETWORK", priority="CRITICAL",  # 15-min response window
    )
    # Force the due date into the past so any comment now is late.
    t.response_due_at = utcnow() - timedelta(hours=1)
    db_session.commit()

    with pytest.raises(DomainError):
        ticket_service.add_comment(db_session, ticket_id=t.id, text="Sorry for the delay", actor=engineer)

    # Rejected request must not have partially applied — no comment, no first_response_at.
    refreshed = ticket_service.get_ticket_or_404(db_session, t.id)
    assert refreshed.first_response_at is None
    assert len(refreshed.comments) == 0

    ticket_service.add_comment(
        db_session, ticket_id=t.id, text="Sorry for the delay", actor=engineer,
        breached_reason="Team was short-staffed overnight")

    refreshed = ticket_service.get_ticket_or_404(db_session, t.id)
    assert refreshed.response_sla_status == "BREACHED"
    assert refreshed.breached_reason == "Team was short-staffed overnight"


# ---------- 4. Resolution ----------

def test_change_status_to_resolved_evaluates_resolution_sla(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="PROBLEM ticket", description="Root cause",
        ticket_type="PROBLEM", category="NETWORK", priority="LOW",  # PROBLEM has no §3 workflow
    )
    ticket_service.change_status(db_session, ticket_id=t.id, target_status="ASSIGNED", actor=engineer)
    ticket_service.change_status(db_session, ticket_id=t.id, target_status="IN_PROGRESS", actor=engineer)
    updated = ticket_service.change_status(db_session, ticket_id=t.id, target_status="RESOLVED", actor=engineer)
    assert updated.resolution_sla_status == "MET"


def test_workflow_status_resolution_evaluates_resolution_sla(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="LOW",
    )
    updated = ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="RESOLVED", actor=engineer)
    assert updated.resolution_sla_status == "MET"
    assert updated.resolved_at is not None


def test_resolution_breach_requires_reason_and_rolls_back(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Server down", description="Prod outage",
        ticket_type="PROBLEM", category="NETWORK", priority="CRITICAL",
    )
    t.resolution_due_at = utcnow() - timedelta(hours=1)
    db_session.commit()
    ticket_service.change_status(db_session, ticket_id=t.id, target_status="ASSIGNED", actor=engineer)
    ticket_service.change_status(db_session, ticket_id=t.id, target_status="IN_PROGRESS", actor=engineer)

    with pytest.raises(DomainError):
        ticket_service.change_status(db_session, ticket_id=t.id, target_status="RESOLVED", actor=engineer)

    refreshed = ticket_service.get_ticket_or_404(db_session, t.id)
    assert refreshed.status != "RESOLVED"
    assert refreshed.resolution_sla_status is None

    updated = ticket_service.change_status(
        db_session, ticket_id=t.id, target_status="RESOLVED", actor=engineer,
        breached_reason="Vendor RCA took longer than expected")
    assert updated.resolution_sla_status == "BREACHED"
    assert updated.breached_reason == "Vendor RCA took longer than expected"


def test_resolution_accounts_for_sla_pause_time(db_session):
    """SPEC §3: the Resolution clock pauses during PEND_USER/PEND_3RDPARTY
    (workflow_status values — see /PROGRESS.md Session 4 for why this session wires
    against those rather than the base `status`/STATUSES field, which has no
    PEND_USER/PEND_3RDPARTY entries)."""
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="LOW",
    )
    # Set the due date just past "now" so resolving immediately would breach...
    t.resolution_due_at = utcnow() + timedelta(seconds=2)
    db_session.commit()

    ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="PEND_USER", actor=engineer)
    import time as _time
    _time.sleep(3)  # ... but the ticket is paused while this elapses ...
    ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="PROGRESSING", actor=engineer)

    updated = ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="RESOLVED", actor=engineer)
    # ... so the effective due date shifted out by the paused duration and this is MET,
    # not BREACHED, even though wall-clock time alone would have missed it.
    assert updated.resolution_sla_status == "MET"
    assert updated.sla_paused_total_seconds >= 3


# ---------- 5. Live AT_RISK/BREACHED status (what sla_scanner.py uses) ----------

def test_business_hours_live_status_on_track_at_risk_and_breached():
    created = utcnow().replace(hour=10, minute=0, second=0, microsecond=0)
    # Ensure created is a weekday for a deterministic business-hours window.
    while created.weekday() > 4:
        created += timedelta(days=1)
    due = created + timedelta(hours=2)  # e.g. a P1 resolution target

    on_track = business_hours_live_status(
        due_at=due, created_at=created, timezone_name="Asia/Kolkata",
        target_minutes=120, now=created + timedelta(minutes=10))
    assert on_track == "ON_TRACK"

    at_risk = business_hours_live_status(
        due_at=due, created_at=created, timezone_name="Asia/Kolkata",
        target_minutes=120, now=created + timedelta(minutes=110))
    assert at_risk == "AT_RISK"

    breached = business_hours_live_status(
        due_at=due, created_at=created, timezone_name="Asia/Kolkata",
        target_minutes=120, now=due + timedelta(minutes=5))
    assert breached == "BREACHED"


def test_business_hours_live_status_none_without_due_date():
    assert business_hours_live_status(
        due_at=None, created_at=utcnow(), timezone_name="Asia/Kolkata",
        target_minutes=120, now=utcnow()) == "NONE"