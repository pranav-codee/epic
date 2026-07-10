"""
Regression tests for the two "fixable now, no deployment needed" issues:
  1. Search endpoint had no exposed pagination (limit/offset) and no cap on limit.
  2. Failed Teams notifications were never retried and had no bounded worker pool.
"""
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./epic_test_immediate_fixes.db")
os.environ.setdefault("AUTH_PROVIDER", "mock")
os.environ.setdefault("TEAMS_NOTIFICATIONS_ENABLED", "false")

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Base, engine
from app import models  # noqa: F401
from app.modules.users.service import upsert_from_identity, set_roles
from app.modules.tickets.service import create_ticket
from app.modules.notifications.models import NotificationRecord
from app.modules.notifications import service as notifications
from app.modules.search import service as search_service
from app.core.rbac import Role
from app.core.security import issue_session, SESSION_COOKIE_NAME


def _make_admin(db, oid, email, name):
    u = upsert_from_identity(db, entra_oid=oid, email=email, display_name=name, department="IT")
    set_roles(db, u.id, [Role.EMPLOYEE.value, Role.SYSTEM_ADMIN.value])
    return u


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


def test_search_pagination_returns_second_page(db_session, client):
    """Before the fix, `limit` was hardcoded server-side and never exposed via the API,
    so a caller could never page past the first 100 results. Create more rows than the
    default page size and confirm offset actually moves the window."""
    admin = _make_admin(db_session, "admin-1", "cara.admin@epl.local", "Cara Admin")
    for i in range(5):
        create_ticket(db_session, creator=admin, title=f"Ticket {i}", description="d",
                      ticket_type="INCIDENT", category="HARDWARE", priority="LOW")

    _login(client, "admin-1", db_session)

    page1 = client.get("/api/v1/search/tickets", params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/api/v1/search/tickets", params={"limit": 2, "offset": 2}).json()

    assert page1["total"] == 5
    assert page1["limit"] == 2 and page1["offset"] == 0
    assert len(page1["results"]) == 2
    assert page2["offset"] == 2
    assert len(page2["results"]) == 2
    # Pages must not overlap.
    ids_page1 = {t["id"] for t in page1["results"]}
    ids_page2 = {t["id"] for t in page2["results"]}
    assert ids_page1.isdisjoint(ids_page2)


def test_search_limit_is_capped_server_side(db_session, client):
    """A caller asking for an absurd page size should be clamped, not allowed to pull
    the entire table in one request."""
    _make_admin(db_session, "admin-2", "cara2.admin@epl.local", "Cara Admin 2")
    _login(client, "admin-2", db_session)

    resp = client.get("/api/v1/search/tickets", params={"limit": 999999}).json()
    assert resp["limit"] == search_service.MAX_PAGE_SIZE


def test_failed_notification_is_scheduled_for_retry_not_dropped(db_session, monkeypatch):
    """Before the fix, a failed Teams send just sat as status=FAILED forever. Now it
    should move to RETRYING with a next_retry_at, and retry_due() should pick it back
    up once that time has passed."""
    admin = _make_admin(db_session, "admin-3", "cara3.admin@epl.local", "Cara Admin 3")
    ticket = create_ticket(db_session, creator=admin, title="Retry me", description="d",
                           ticket_type="INCIDENT", category="HARDWARE", priority="LOW")

    # Force the Teams channel to fail so we can observe the retry scheduling.
    async def _always_fail(*args, **kwargs):
        return False, "simulated webhook timeout"
    monkeypatch.setattr(notifications._channel, "send", _always_fail)

    record = notifications.dispatch(db_session, event="TICKET_CREATED", ticket=ticket)

    # dispatch() fires the send on a background worker; wait briefly for it to land.
    import time
    for _ in range(50):
        db_session.expire_all()
        r = db_session.query(NotificationRecord).filter(NotificationRecord.id == record.id).one()
        if r.status != "PENDING":
            break
        time.sleep(0.05)

    assert r.status == "RETRYING"
    assert r.retry_count == 1
    assert r.next_retry_at is not None

    # Simulate the backoff window having elapsed, then confirm the sweep picks it up.
    r.next_retry_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    picked_up = notifications.retry_due(db_session)
    assert picked_up == 1
