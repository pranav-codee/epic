"""
Regression tests for the remediation pass:
  1. Ticket numbering stays unique under concurrent creation, including on SQLite.
  2. A revoked session (role change / explicit force-logout) is rejected immediately,
     not just after the cookie's natural 8h expiry.
"""
import os, sys, pathlib, threading
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./epic_test_remediation.db")
os.environ.setdefault("AUTH_PROVIDER", "mock")
os.environ.setdefault("TEAMS_NOTIFICATIONS_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Base, engine
from app import models  # noqa: F401
from app.modules.users.service import upsert_from_identity, set_roles, revoke_sessions
from app.modules.tickets.service import create_ticket
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


def _login(client, oid, db):
    from app.modules.users.models import UserProfile
    u = db.query(UserProfile).filter(UserProfile.entra_object_id == oid).one_or_none()
    token = issue_session(oid, u.session_version)
    client.cookies.set(SESSION_COOKIE_NAME, token)


def test_ticket_numbers_stay_unique_under_concurrent_creation(db_session):
    """20 threads each open their own session against the same SQLite file and create a
    ticket concurrently. Before the fix this could produce duplicate EPIC-YYYY-NNNNNN
    numbers because the increment was read-modify-write in Python."""
    creator = upsert_from_identity(
        db_session, entra_oid="mock-race@epl.local",
        email="race@epl.local", display_name="Race Tester", department="Ops",
    )
    creator_id = creator.id

    numbers = []
    lock = threading.Lock()
    errors = []

    def worker():
        s = SessionLocal()
        try:
            from app.modules.users.models import UserProfile
            u = s.query(UserProfile).filter(UserProfile.id == creator_id).one()
            t = create_ticket(
                s, creator=u, title="Race ticket", description="concurrency check",
                ticket_type="INCIDENT", category="HARDWARE", priority="LOW",
            )
            with lock:
                numbers.append(t.ticket_number)
        except Exception as e:  # pragma: no cover
            with lock:
                errors.append(e)
        finally:
            s.close()

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert not errors, f"worker errors: {errors}"
    assert len(numbers) == 20
    assert len(set(numbers)) == 20, f"duplicate ticket numbers were issued: {numbers}"


def test_revoked_session_is_rejected_immediately(db_session, client):
    user = upsert_from_identity(
        db_session, entra_oid="mock-revoke@epl.local",
        email="revoke@epl.local", display_name="Revoke Me", department="Ops",
    )
    _login(client, "mock-revoke@epl.local", db_session)

    ok = client.get("/api/v1/auth/me")
    assert ok.status_code == 200

    revoke_sessions(db_session, user.id)

    still_using_old_cookie = client.get("/api/v1/auth/me")
    assert still_using_old_cookie.status_code == 401


def test_role_change_revokes_existing_sessions(db_session, client):
    admin = upsert_from_identity(
        db_session, entra_oid="mock-admin2@epl.local",
        email="admin2@epl.local", display_name="Admin Two", department="IT",
    )
    set_roles(db_session, admin.id, [Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value])

    target = upsert_from_identity(
        db_session, entra_oid="mock-target@epl.local",
        email="target@epl.local", display_name="Target User", department="Ops",
    )

    target_client = TestClient(app)
    _login(target_client, "mock-target@epl.local", db_session)
    assert target_client.get("/api/v1/auth/me").status_code == 200

    admin_client = TestClient(app)
    _login(admin_client, "mock-admin2@epl.local", db_session)
    r = admin_client.patch(f"/api/v1/users/{target.id}/roles",
                           json={"roles": [Role.EMPLOYEE.value, Role.IT_ENGINEER.value]})
    assert r.status_code == 200

    assert target_client.get("/api/v1/auth/me").status_code == 401