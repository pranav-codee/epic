"""
Lightweight session token utilities. We issue a signed cookie containing the user's
Entra object id; on each request we resolve the UserProfile from DB. Tokens are short-lived.
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from ..config import get_settings

_settings = get_settings()
_serializer = URLSafeTimedSerializer(_settings.SESSION_SECRET, salt="epic-session-v1")

SESSION_COOKIE_NAME = "epic_session"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60  # 8 hours, aligns with a typical workday


def issue_session(entra_object_id: str) -> str:
    return _serializer.dumps({"oid": entra_object_id})


def read_session(token: str) -> str | None:
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data.get("oid")
    except (BadSignature, SignatureExpired):
        return None
