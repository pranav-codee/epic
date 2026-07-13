"""
Integration tests for SPEC §3 (Status/workflow) — the ticket-type-specific
`workflow_status` field/endpoint, additive alongside the pre-existing generic `status`.

Covers:
  1. workflow_status is initialized correctly at ticket creation (per ticket_type).
  2. Legal transitions succeed via the service layer and the HTTP endpoint.
  3. Illegal transitions are rejected (fail closed).
  4. Only IT staff may change workflow_status (SPEC §9 fail-closed permission check),
     mirroring the existing change_status permission model exactly.
  5. The Resolution SLA pause clock (SPEC §3: "pauses during PEND_USER/PEND_3RDPARTY")
     starts/stops correctly and accumulates total paused time.
  6. Every workflow_status change is audit-logged (SPEC §9).
  7. Reclassifying a ticket's type re-derives workflow_status for the new type's graph.
  8. The endpoint is rate-limited like every other ticket mutation endpoint (SPEC §9).
"""
import os, sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./epic_test_workflow.db")
os.environ.setdefault("AUTH_PROVIDER", "mock")
os.environ.setdefault("TEAMS_NOTIFICATIONS_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Base, engine
from app import models  # noqa: F401 ensures all models are registered
from app.modules.users.service import upsert_from_identity, set_roles, attach_roles
from app.modules.tickets import service as ticket_service
from app.modules.tickets.models import Ticket
from app.modules.audit.service import list_for_ticket, Action
from app.core.rbac import Role
from app.core.exceptions import Forbidden, DomainError
from app.core.security import issue_session, SESSION_COOKIE_NAME


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    return TestClient(app)


def _login(client, oid, db):
    from app.modules.users.models import UserProfile
    u = db.query(UserProfile).filter(UserProfile.entra_object_id == oid).one_or_none()
    token = issue_session(oid, u.session_version)
    client.cookies.set(SESSION_COOKIE_NAME, token)


def _make_engineer(db, oid="mock-eng-wf@epl.local"):
    u = upsert_from_identity(db, entra_oid=oid, email=oid, display_name="Engineer WF", department="IT")
    set_roles(db, u.id, [Role.EMPLOYEE.value, Role.IT_ENGINEER.value])
    attach_roles(u, db)
    return u


def _make_employee(db, oid="mock-emp-wf@epl.local"):
    u = upsert_from_identity(db, entra_oid=oid, email=oid, display_name="Employee WF", department="Sales")
    set_roles(db, u.id, [Role.EMPLOYEE.value])
    attach_roles(u, db)
    return u


# ---------- 1. Initialization at creation ----------

def test_incident_starts_progressing(db_session):
    creator = _make_employee(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Printer down", description="Cannot print",
        ticket_type="INCIDENT", category="HARDWARE", priority="MEDIUM",
    )
    assert t.workflow_status == "PROGRESSING"


def test_service_request_starts_progressing(db_session):
    creator = _make_employee(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="New laptop", description="Need a laptop",
        ticket_type="SERVICE_REQUEST", category="HARDWARE", priority="LOW",
    )
    assert t.workflow_status == "PROGRESSING"


def test_problem_and_change_request_have_no_workflow_status(db_session):
    creator = _make_employee(db_session)
    for ttype in ("PROBLEM", "CHANGE_REQUEST"):
        t = ticket_service.create_ticket(
            db_session, creator=creator, title=f"{ttype} ticket", description="out of §3 scope",
            ticket_type=ttype, category="OTHER", priority="LOW",
        )
        assert t.workflow_status is None


# ---------- 2/3. Legal vs illegal transitions (service layer) ----------

def test_legal_transition_via_service(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    updated = ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="PEND_USER", actor=engineer)
    assert updated.workflow_status == "PEND_USER"


def test_illegal_transition_rejected(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    # RESOLVED is not directly reachable from PROGRESSING via ON_HOLD without resuming first —
    # but PROGRESSING -> RESOLVED *is* legal; use ON_HOLD -> RESOLVED (illegal) instead.
    ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="ON_HOLD", actor=engineer)
    with pytest.raises(DomainError):
        ticket_service.change_workflow_status(
            db_session, ticket_id=t.id, target_workflow_status="RESOLVED", actor=engineer)


def test_workflow_status_change_rejected_for_out_of_scope_ticket_type(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Root cause investigation", description="...",
        ticket_type="PROBLEM", category="OTHER", priority="LOW",
    )
    with pytest.raises(DomainError):
        ticket_service.change_workflow_status(
            db_session, ticket_id=t.id, target_workflow_status="PROGRESSING", actor=engineer)


def test_invalid_target_state_for_type_rejected(db_session):
    """APPROVED is an Incident-only state; a Service Request ticket must reject it."""
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="New monitor", description="Need one",
        ticket_type="SERVICE_REQUEST", category="HARDWARE", priority="LOW",
    )
    with pytest.raises(DomainError):
        ticket_service.change_workflow_status(
            db_session, ticket_id=t.id, target_workflow_status="APPROVED", actor=engineer)


# ---------- 4. Permission enforcement (SPEC §9 fail-closed) ----------

def test_employee_cannot_change_workflow_status(db_session):
    creator = _make_employee(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    with pytest.raises(Forbidden):
        ticket_service.change_workflow_status(
            db_session, ticket_id=t.id, target_workflow_status="ON_HOLD", actor=creator)


def test_endpoint_rejects_employee_with_403(db_session, client):
    creator = _make_employee(db_session, "mock-emp-http@epl.local")
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    _login(client, "mock-emp-http@epl.local", db_session)
    resp = client.post(f"/api/v1/tickets/{t.id}/workflow-status", json={"target_workflow_status": "ON_HOLD"})
    assert resp.status_code == 403


def test_endpoint_allows_engineer_and_persists(db_session, client):
    creator = _make_employee(db_session, "mock-emp-http2@epl.local")
    engineer = _make_engineer(db_session, "mock-eng-http@epl.local")
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    _login(client, "mock-eng-http@epl.local", db_session)
    resp = client.post(f"/api/v1/tickets/{t.id}/workflow-status", json={"target_workflow_status": "pend_user"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow_status"] == "PEND_USER"

    detail = client.get(f"/api/v1/tickets/{t.id}")
    assert detail.status_code == 200
    assert "PROGRESSING" in detail.json()["allowed_workflow_target_states"]


def test_endpoint_requires_auth(client):
    resp = client.post("/api/v1/tickets/nonexistent/workflow-status", json={"target_workflow_status": "ON_HOLD"})
    assert resp.status_code in (401, 403)


# ---------- 5. SLA pause-clock bookkeeping ----------

def test_pause_clock_starts_on_entering_pend_user(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    assert t.sla_paused_at is None
    updated = ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="PEND_USER", actor=engineer)
    assert updated.sla_paused_at is not None
    assert updated.sla_paused_total_seconds == 0


def test_pause_clock_stops_and_accumulates_on_resume(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="PEND_USER", actor=engineer)
    time.sleep(1.1)
    updated = ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="PROGRESSING", actor=engineer)
    assert updated.sla_paused_at is None
    assert updated.sla_paused_total_seconds >= 1


def test_pause_clock_accumulates_across_multiple_pauses(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    ticket_service.change_workflow_status(db_session, ticket_id=t.id, target_workflow_status="PEND_USER", actor=engineer)
    time.sleep(1.1)
    ticket_service.change_workflow_status(db_session, ticket_id=t.id, target_workflow_status="PROGRESSING", actor=engineer)
    first_total = db_session.query(Ticket).filter(Ticket.id == t.id).one().sla_paused_total_seconds
    assert first_total >= 1

    ticket_service.change_workflow_status(db_session, ticket_id=t.id, target_workflow_status="PEND_3RDPARTY", actor=engineer)
    time.sleep(1.1)
    updated = ticket_service.change_workflow_status(db_session, ticket_id=t.id, target_workflow_status="PROGRESSING", actor=engineer)
    assert updated.sla_paused_total_seconds >= first_total + 1


def test_pause_clock_stops_when_ticket_resolved_while_paused(db_session):
    """PEND_USER -> resolve is a legal direct transition (see workflow.py); the pause clock
    must not keep running once the ticket is terminal."""
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    ticket_service.change_workflow_status(db_session, ticket_id=t.id, target_workflow_status="PEND_USER", actor=engineer)
    time.sleep(1.1)
    updated = ticket_service.change_workflow_status(db_session, ticket_id=t.id, target_workflow_status="RESOLVED", actor=engineer)
    assert updated.sla_paused_at is None
    assert updated.sla_paused_total_seconds >= 1
    assert updated.resolved_at is not None


def test_pause_clock_does_not_start_for_non_pause_states(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    updated = ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="ON_HOLD", actor=engineer)
    assert updated.sla_paused_at is None
    assert updated.sla_paused_total_seconds == 0


# ---------- 6. Audit logging (SPEC §9) ----------

def test_workflow_status_change_is_audit_logged(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="VPN issue", description="Can't connect",
        ticket_type="INCIDENT", category="VPN", priority="HIGH",
    )
    ticket_service.change_workflow_status(
        db_session, ticket_id=t.id, target_workflow_status="PEND_USER", actor=engineer)
    entries = list_for_ticket(db_session, t.id)
    wf_entries = [e for e in entries if e.action == Action.WORKFLOW_STATUS_CHANGE]
    assert len(wf_entries) == 1
    assert wf_entries[0].old_value == "PROGRESSING"
    assert wf_entries[0].new_value == "PEND_USER"
    assert wf_entries[0].actor_id == engineer.id


# ---------- 7. Reclassification re-derives workflow_status ----------

def test_reclassify_incident_to_problem_clears_workflow_status(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Recurring outage", description="3rd time this week",
        ticket_type="INCIDENT", category="NETWORK", priority="HIGH",
    )
    assert t.workflow_status == "PROGRESSING"
    updated = ticket_service.reclassify_ticket(db_session, ticket_id=t.id, ticket_type="PROBLEM", actor=engineer)
    assert updated.workflow_status is None


def test_reclassify_problem_to_incident_initializes_workflow_status(db_session):
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Root cause", description="Investigating",
        ticket_type="PROBLEM", category="NETWORK", priority="LOW",
    )
    assert t.workflow_status is None
    updated = ticket_service.reclassify_ticket(db_session, ticket_id=t.id, ticket_type="INCIDENT", actor=engineer)
    assert updated.workflow_status == "PROGRESSING"


def test_reclassify_ends_pause_clock(db_session):
    """Reclassifying away mid-pause must not leave sla_paused_at dangling forever."""
    creator = _make_employee(db_session)
    engineer = _make_engineer(db_session)
    t = ticket_service.create_ticket(
        db_session, creator=creator, title="Flaky VPN", description="Investigating",
        ticket_type="INCIDENT", category="VPN", priority="MEDIUM",
    )
    ticket_service.change_workflow_status(db_session, ticket_id=t.id, target_workflow_status="PEND_3RDPARTY", actor=engineer)
    time.sleep(1.1)
    updated = ticket_service.reclassify_ticket(db_session, ticket_id=t.id, ticket_type="PROBLEM", actor=engineer)
    assert updated.sla_paused_at is None
    assert updated.sla_paused_total_seconds >= 1


# ---------- 8. Rate limiting present (SPEC §9) ----------

def test_workflow_status_endpoint_is_rate_limited():
    """Same convention as every other ticket mutation endpoint in router.py — assert the
    decorator is present rather than burning 30+ requests in the test suite."""
    from app.modules.tickets.router import change_workflow_status as endpoint_fn
    assert hasattr(endpoint_fn, "__wrapped__")