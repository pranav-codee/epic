"""
Regression tests for the ticketed remediation pass:

  1. Broken Access Control     — last SYSTEM_ADMIN can no longer be demoted (lockout guard)
  2. Functional defect         — employee self-cancel is reachable again
  3. Broken Access Control     — ticket assignee must hold a support-staff role
  4. Improper State Validation — priority/type can no longer change on a CLOSED/CANCELLED ticket
  5. A09 Logging & Monitoring  — role grants/revocations, force-logout, and logins are audited
  6. Stored Content Injection  — ticket title is sanitized before it reaches the Teams card
  7. Resource Exhaustion       — attachment count/size is capped per ticket and per user
"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./epic_test_remediation2.db")
os.environ.setdefault("AUTH_PROVIDER", "mock")
os.environ.setdefault("TEAMS_NOTIFICATIONS_ENABLED", "false")

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Base, engine
from app import models  # noqa: F401
from app.modules.users.service import upsert_from_identity, set_roles
from app.modules.users.models import UserRoleAssignment
from app.modules.tickets.service import create_ticket, change_status
from app.modules.audit.service import search as audit_search, Action
from app.modules.notifications.templates import build as build_notification
from app.core.rbac import Role
from app.core.security import issue_session, SESSION_COOKIE_NAME
from app.config import get_settings


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


def _make_user(db, oid, email, name, roles=(Role.EMPLOYEE.value,)):
    u = upsert_from_identity(db, entra_oid=oid, email=email, display_name=name, department="Ops")
    set_roles(db, u.id, list(roles))
    db.refresh(u)
    return u


# ---------- 1. Last SYSTEM_ADMIN cannot be demoted ----------

def test_cannot_remove_last_system_admin(db_session):
    admin = _make_user(db_session, "mock-lastadmin@epl.local", "lastadmin@epl.local",
                       "Last Admin", roles=[Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value])
    with pytest.raises(ValueError, match="last remaining system administrator"):
        set_roles(db_session, admin.id, [Role.EMPLOYEE.value])

    # Role must be unchanged after the failed attempt.
    roles = {r.role for r in db_session.query(UserRoleAssignment)
             .filter(UserRoleAssignment.user_id == admin.id).all()}
    assert Role.SYSTEM_ADMIN.value in roles


def test_can_demote_admin_when_another_admin_exists(db_session):
    admin1 = _make_user(db_session, "mock-a1@epl.local", "a1@epl.local", "Admin One",
                        roles=[Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value])
    _make_user(db_session, "mock-a2@epl.local", "a2@epl.local", "Admin Two",
              roles=[Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value])

    # Now safe — a second admin exists.
    set_roles(db_session, admin1.id, [Role.EMPLOYEE.value])
    roles = {r.role for r in db_session.query(UserRoleAssignment)
             .filter(UserRoleAssignment.user_id == admin1.id).all()}
    assert Role.SYSTEM_ADMIN.value not in roles


def test_update_roles_endpoint_rejects_last_admin_self_demote(db_session, client):
    admin = _make_user(db_session, "mock-soleadmin@epl.local", "soleadmin@epl.local",
                       "Sole Admin", roles=[Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value])
    _login(client, "mock-soleadmin@epl.local", db_session)
    r = client.patch(f"/api/v1/users/{admin.id}/roles", json={"roles": [Role.EMPLOYEE.value]})
    assert r.status_code == 400


# ---------- 2. Employee self-cancel is reachable ----------

def test_employee_can_cancel_own_open_ticket(db_session, client):
    emp = _make_user(db_session, "mock-canceler@epl.local", "canceler@epl.local", "Canceler")
    _login(client, "mock-canceler@epl.local", db_session)

    created = client.post("/api/v1/tickets", json={
        "title": "Printer jam", "description": "Paper stuck in tray 2",
        "ticket_type": "INCIDENT", "category": "HARDWARE", "priority": "LOW",
    })
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    cancel = client.post(f"/api/v1/tickets/{ticket_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"


def test_employee_cannot_cancel_someone_elses_ticket(db_session, client):
    owner = _make_user(db_session, "mock-owner@epl.local", "owner@epl.local", "Owner")
    _make_user(db_session, "mock-nosy@epl.local", "nosy@epl.local", "Nosy")

    t = create_ticket(db_session, creator=owner, title="VPN broken", description="Can't connect",
                      ticket_type="INCIDENT", category="VPN", priority="MEDIUM")

    _login(client, "mock-nosy@epl.local", db_session)
    r = client.post(f"/api/v1/tickets/{t.id}/cancel")
    assert r.status_code == 403


# ---------- 3. Assignee must be support staff ----------

def test_cannot_assign_ticket_to_employee(db_session, client):
    engineer = _make_user(db_session, "mock-eng@epl.local", "eng@epl.local", "Engineer",
                          roles=[Role.EMPLOYEE.value, Role.IT_ENGINEER.value])
    employee = _make_user(db_session, "mock-plainemp@epl.local", "plainemp@epl.local", "Plain Employee")
    creator = _make_user(db_session, "mock-creator@epl.local", "creator@epl.local", "Creator")

    t = create_ticket(db_session, creator=creator, title="Laptop won't boot", description="Black screen",
                      ticket_type="INCIDENT", category="HARDWARE", priority="HIGH")

    _login(client, "mock-eng@epl.local", db_session)
    r = client.post(f"/api/v1/tickets/{t.id}/assign", json={"assignee_id": employee.id})
    assert r.status_code == 400
    assert "support staff" in r.json()["detail"]


def test_can_assign_ticket_to_it_engineer(db_session, client):
    engineer = _make_user(db_session, "mock-eng2@epl.local", "eng2@epl.local", "Engineer Two",
                          roles=[Role.EMPLOYEE.value, Role.IT_ENGINEER.value])
    other_engineer = _make_user(db_session, "mock-eng3@epl.local", "eng3@epl.local", "Engineer Three",
                                roles=[Role.EMPLOYEE.value, Role.IT_ENGINEER.value])
    creator = _make_user(db_session, "mock-creator2@epl.local", "creator2@epl.local", "Creator Two")

    t = create_ticket(db_session, creator=creator, title="Wifi down", description="Whole floor",
                      ticket_type="INCIDENT", category="NETWORK", priority="CRITICAL")

    _login(client, "mock-eng2@epl.local", db_session)
    r = client.post(f"/api/v1/tickets/{t.id}/assign", json={"assignee_id": other_engineer.id})
    assert r.status_code == 200
    assert r.json()["status"] == "ASSIGNED"


# ---------- 4. Priority/type immutable once CLOSED/CANCELLED ----------

def test_cannot_change_priority_after_closed(db_session, client):
    from app.modules.users.service import attach_roles
    engineer = _make_user(db_session, "mock-eng4@epl.local", "eng4@epl.local", "Engineer Four",
                          roles=[Role.EMPLOYEE.value, Role.IT_ENGINEER.value])
    attach_roles(engineer, db_session)
    creator = _make_user(db_session, "mock-creator3@epl.local", "creator3@epl.local", "Creator Three")

    t = create_ticket(db_session, creator=creator, title="App crash", description="Excel crashes",
                      ticket_type="INCIDENT", category="APPLICATION", priority="MEDIUM")

    from app.modules.tickets import service as tsvc
    tsvc.assign_ticket(db_session, ticket_id=t.id, assignee_id=engineer.id, actor=engineer)
    tsvc.change_status(db_session, ticket_id=t.id, target_status="IN_PROGRESS", actor=engineer)
    tsvc.change_status(db_session, ticket_id=t.id, target_status="RESOLVED", actor=engineer)
    tsvc.change_status(db_session, ticket_id=t.id, target_status="CLOSED", actor=engineer)

    _login(client, "mock-eng4@epl.local", db_session)
    r = client.post(f"/api/v1/tickets/{t.id}/priority", json={"priority": "CRITICAL"})
    assert r.status_code == 400
    assert "terminal state" in r.json()["detail"]

    r2 = client.post(f"/api/v1/tickets/{t.id}/reclassify", json={"ticket_type": "PROBLEM"})
    assert r2.status_code == 400


# ---------- 5. Audit trail for role changes / force-logout / logins ----------

def test_role_change_and_force_logout_are_audited(db_session, client):
    admin = _make_user(db_session, "mock-auditadmin@epl.local", "auditadmin@epl.local",
                       "Audit Admin", roles=[Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value])
    target = _make_user(db_session, "mock-audittarget@epl.local", "audittarget@epl.local",
                        "Audit Target")

    _login(client, "mock-auditadmin@epl.local", db_session)
    r = client.patch(f"/api/v1/users/{target.id}/roles",
                     json={"roles": [Role.EMPLOYEE.value, Role.IT_ENGINEER.value]})
    assert r.status_code == 200

    entries = audit_search(db_session, action=Action.ROLE_GRANT)
    assert any(e.actor_id == admin.id for e in entries)

    logout = client.post(f"/api/v1/users/{target.id}/revoke-sessions")
    assert logout.status_code == 204
    fl_entries = audit_search(db_session, action=Action.FORCE_LOGOUT)
    assert any(e.actor_id == admin.id for e in fl_entries)


def test_login_is_audited(db_session, client):
    from app.core.security import issue_oauth_state
    from app.modules.auth.router import OAUTH_STATE_COOKIE_NAME

    # /callback binds the `state` query param to a same-name cookie set by /login (CSRF
    # fix). Generate a fresh nonce per call and set the matching cookie ourselves,
    # rather than relying on a shared/hardcoded state string, so this test is
    # order-independent and doesn't collide with any other test issuing a state token.
    state = issue_oauth_state(f"test-state-{os.urandom(8).hex()}")
    client.cookies.set(OAUTH_STATE_COOKIE_NAME, state)

    r = client.get(f"/api/v1/auth/callback?state={state}&email=newlogin@epl.local",
                   follow_redirects=False)
    assert r.status_code == 307

    entries = audit_search(db_session, action=Action.LOGIN)
    assert any(e.actor_email == "newlogin@epl.local" for e in entries)


# ---------- 6. Ticket title sanitized before Teams notification ----------

def test_malicious_ticket_title_is_sanitized_for_teams():
    class FakeTicket:
        ticket_number = "EPIC-2026-000001"
        title = "[Password expired - click here](https://evil.example/phish)"
        status = "OPEN"
        priority = "HIGH"
        category = "SECURITY"
        id = "abc123"

    title, text, facts, url = build_notification("TICKET_CREATED", FakeTicket())
    # The markdown link syntax must not survive unescaped — otherwise Teams renders a
    # clickable link that looks legitimate (phishing IT staff).
    assert "](https://evil.example/phish)" not in text
    assert "\\[" in text or "\\(" in text


# ---------- 7. Attachment count/size caps ----------

def test_attachment_count_cap_per_ticket(db_session, client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ATTACHMENT_MAX_PER_TICKET", 2)

    emp = _make_user(db_session, "mock-uploader@epl.local", "uploader@epl.local", "Uploader")
    _login(client, "mock-uploader@epl.local", db_session)

    created = client.post("/api/v1/tickets", json={
        "title": "Need help", "description": "Attaching logs",
        "ticket_type": "INCIDENT", "category": "SOFTWARE", "priority": "LOW",
    })
    ticket_id = created.json()["id"]

    for i in range(2):
        resp = client.post(f"/api/v1/tickets/{ticket_id}/attachments",
                           files={"file": (f"log{i}.txt", io.BytesIO(b"hello"), "text/plain")})
        assert resp.status_code == 201

    over_cap = client.post(f"/api/v1/tickets/{ticket_id}/attachments",
                           files={"file": ("log_extra.txt", io.BytesIO(b"hello"), "text/plain")})
    assert over_cap.status_code == 413