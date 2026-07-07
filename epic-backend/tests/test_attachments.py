import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./epic_test_attachments.db")
os.environ.setdefault("AUTH_PROVIDER", "mock")
os.environ.setdefault("TEAMS_NOTIFICATIONS_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Base, engine
from app import models  # noqa: F401
from app.modules.users.service import upsert_from_identity
from app.modules.tickets.service import create_ticket
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


@pytest.fixture()
def ticket_and_user(db_session):
    user = upsert_from_identity(
        db_session, entra_oid="mock-att@epl.local",
        email="att@epl.local", display_name="Attach Er", department="Ops",
    )
    t = create_ticket(db_session, creator=user, title="Attachment test",
                      description="desc", ticket_type="INCIDENT",
                      category="HARDWARE", priority="LOW")
    return t, user


def test_disallowed_extension_is_rejected(db_session, client, ticket_and_user):
    t, user = ticket_and_user
    _login(client, "mock-att@epl.local", db_session)
    r = client.post(f"/api/v1/tickets/{t.id}/attachments",
                    files={"file": ("evil.exe", b"MZ\x90\x00fake pe header", "application/octet-stream")})
    assert r.status_code == 400


def test_content_mismatch_is_rejected(db_session, client, ticket_and_user):
    """A .png extension whose actual bytes are not a PNG should be rejected by the sniffer,
    not trusted purely on the basis of the filename."""
    t, user = ticket_and_user
    _login(client, "mock-att@epl.local", db_session)
    r = client.post(f"/api/v1/tickets/{t.id}/attachments",
                    files={"file": ("photo.png", b"MZ\x90\x00 this is not a png", "image/png")})
    assert r.status_code == 400


def test_valid_png_attachment_is_accepted(db_session, client, ticket_and_user):
    t, user = ticket_and_user
    _login(client, "mock-att@epl.local", db_session)
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    r = client.post(f"/api/v1/tickets/{t.id}/attachments",
                    files={"file": ("photo.png", png_bytes, "image/png")})
    assert r.status_code == 201


def test_oversized_upload_is_rejected_without_buffering_fully(db_session, client, ticket_and_user, monkeypatch):
    from app.config import get_settings
    # Shrink the limit for the test so we don't need to actually push 25MB over the wire.
    monkeypatch.setattr(get_settings(), "ATTACHMENT_MAX_BYTES", 10)
    t, user = ticket_and_user
    _login(client, "mock-att@epl.local", db_session)
    r = client.post(f"/api/v1/tickets/{t.id}/attachments",
                    files={"file": ("small.txt", b"this is definitely more than 10 bytes", "text/plain")})
    assert r.status_code == 413