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


def issue_session(entra_object_id: str, session_version: str) -> str:
    return _serializer.dumps({"oid": entra_object_id, "sv": session_version})


def read_session(token: str) -> dict | None:
    """Returns {"oid": ..., "sv": ...} or None if the token is missing/invalid/expired."""
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        if "oid" not in data:
            return None
        return data
    except (BadSignature, SignatureExpired):
        return None


# --- OAuth "state" CSRF token ---
# Signed + self-expiring, so no server-side dict is needed (that approach leaked memory
# and didn't work across multiple app instances behind a load balancer).
_oauth_state_serializer = URLSafeTimedSerializer(_settings.SESSION_SECRET, salt="epic-oauth-state-v1")
OAUTH_STATE_MAX_AGE_SECONDS = 10 * 60  # 10 minutes is plenty for a login redirect round-trip


def issue_oauth_state(nonce: str) -> str:
    return _oauth_state_serializer.dumps({"n": nonce})


def read_oauth_state(token: str) -> bool:
    """Returns True if the state token is a valid, unexpired token this server issued."""
    try:
        _oauth_state_serializer.loads(token, max_age=OAUTH_STATE_MAX_AGE_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False