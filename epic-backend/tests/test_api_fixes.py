"""
Regression tests for:
  1. GET /users 500 error (EmailStr rejected .local mock domains at response-serialization time)
  2. Ticket type classification (INCIDENT / SERVICE_REQUEST / PROBLEM / CHANGE_REQUEST)
  3. Audit history now attributes each entry to the acting user ("who" column)
"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./epic_test_api.db")
os.environ.setdefault("AUTH_PROVIDER", "mock")
os.environ.setdefault("TEAMS_NOTIFICATIONS_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Base, engine
from app import models  # noqa: F401 ensures models are registered
from app.modules.users.service import upsert_from_identity, set_roles
from app.core.rbac import Role
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


def _login(client, oid):
    token = issue_session(oid)
    client.cookies.set(SESSION_COOKIE_NAME, token)


def test_list_users_with_local_domain_emails_does_not_500(db_session, client):
    """Mock/dev identities use @*.local addresses; response serialization must not choke on them."""
    admin = upsert_from_identity(
        db_session, entra_oid="mock-admin@epl.local",
        email="admin@epl.local", display_name="Admin User", department="IT",
    )
    set_roles(db_session, admin.id, [Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value])

    _login(client, "mock-admin@epl.local")
    r = client.get("/api/v1/users")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert "admin@epl.local" in emails


def test_create_ticket_requires_valid_ticket_type(db_session, client):
    emp = upsert_from_identity(
        db_session, entra_oid="mock-emp@epl.local",
        email="emp@epl.local", display_name="Employee One", department="Ops",
    )
    _login(client, "mock-emp@epl.local")

    bad = client.post("/api/v1/tickets", json={
        "title": "Broken thing", "description": "Something is broken",
        "ticket_type": "NOT_A_TYPE", "category": "HARDWARE", "priority": "LOW",
    })
    assert bad.status_code == 400

    good = client.post("/api/v1/tickets", json={
        "title": "New laptop request", "description": "Requesting a new laptop",
        "ticket_type": "service_request", "category": "hardware", "priority": "low",
    })
    assert good.status_code == 201
    assert good.json()["ticket_type"] == "SERVICE_REQUEST"


def test_engineer_can_reclassify_ticket_and_employee_cannot(db_session, client):
    emp = upsert_from_identity(
        db_session, entra_oid="mock-emp2@epl.local",
        email="emp2@epl.local", display_name="Employee Two", department="Ops",
    )
    eng = upsert_from_identity(
        db_session, entra_oid="mock-eng@epl.local",
        email="eng@epl.local", display_name="Engineer One", department="IT",
    )
    set_roles(db_session, eng.id, [Role.EMPLOYEE.value, Role.IT_ENGINEER.value])

    _login(client, "mock-emp2@epl.local")
    created = client.post("/api/v1/tickets", json={
        "title": "VPN drops constantly", "description": "VPN disconnects every few minutes",
        "ticket_type": "INCIDENT", "category": "VPN", "priority": "HIGH",
    }).json()
    ticket_id = created["id"]

    # Employee cannot reclassify.
    forbidden = client.post(f"/api/v1/tickets/{ticket_id}/reclassify", json={"ticket_type": "PROBLEM"})
    assert forbidden.status_code == 403

    # Engineer can promote a recurring incident to a problem.
    _login(client, "mock-eng@epl.local")
    ok = client.post(f"/api/v1/tickets/{ticket_id}/reclassify", json={"ticket_type": "PROBLEM"})
    assert ok.status_code == 200
    assert ok.json()["ticket_type"] == "PROBLEM"


def test_audit_history_reports_who_made_each_change(db_session, client):
    emp = upsert_from_identity(
        db_session, entra_oid="mock-emp3@epl.local",
        email="emp3@epl.local", display_name="Employee Three", department="Ops",
    )
    eng = upsert_from_identity(
        db_session, entra_oid="mock-eng2@epl.local",
        email="eng2@epl.local", display_name="Engineer Two", department="IT",
    )
    set_roles(db_session, eng.id, [Role.EMPLOYEE.value, Role.IT_ENGINEER.value])

    _login(client, "mock-emp3@epl.local")
    created = client.post("/api/v1/tickets", json={
        "title": "Printer offline", "description": "The 3rd floor printer is offline",
        "ticket_type": "INCIDENT", "category": "HARDWARE", "priority": "MEDIUM",
    }).json()
    ticket_id = created["id"]

    _login(client, "mock-eng2@epl.local")
    client.post(f"/api/v1/tickets/{ticket_id}/priority", json={"priority": "HIGH"})

    history = client.get(f"/api/v1/audit/tickets/{ticket_id}").json()
    by_action = {h["action"]: h for h in history}

    assert by_action["CREATE"]["actor_name"] == "Employee Three"
    assert by_action["PRIORITY_CHANGE"]["actor_name"] == "Engineer Two"
    # Raw UUID must not be the only identifying info — actor_id is still present for auditors,
    # but actor_name is now populated for the UI's "Who" column.
    assert by_action["CREATE"]["actor_id"] is not None