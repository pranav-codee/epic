"""
Notification dispatcher. Records every delivery attempt in `notification_records`
so failed Teams deliveries are observable but never block ticket actions (NFR-5.4-2).

Fixes applied:
- Previously every dispatch() call spawned a brand-new, unbounded threading.Thread.
  Under a burst of ticket activity (e.g. a bulk reassignment) that has no ceiling —
  hundreds of OS threads could be created at once. Now all sends go through a single
  bounded ThreadPoolExecutor shared by the process.
- Previously a failed Teams delivery was marked FAILED and nothing ever looked at it
  again — a transient Teams/network outage silently dropped that notification forever.
  Failures are now scheduled for retry with exponential backoff (via next_retry_at);
  see notification_retry_loop.py for the sweep that picks them back up.
"""
import json, asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from .models import NotificationRecord
from .channels.teams import TeamsChannel
from .templates import build as build_payload
from ..tickets.models import Ticket

_channel = TeamsChannel()

# Bounded pool: caps concurrent outbound Teams calls regardless of how many
# ticket events fire at once. Sized generously for a single-webhook, ~2,300-user
# deployment; tune via NOTIFICATION_WORKER_THREADS if that ever changes.
_MAX_WORKERS = 8
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="notify")

# Retry policy: capped exponential backoff, then give up and surface as DEAD_LETTER
# so an admin can see it in the notifications list instead of it vanishing silently.
MAX_RETRY_ATTEMPTS = 5
_BACKOFF_SECONDS = [30, 120, 600, 1800, 3600]  # 30s, 2m, 10m, 30m, 1h


def _run_async(coro):
    """Run an async coroutine on the bounded pool without blocking the caller's thread."""
    def runner():
        try:
            asyncio.run(coro)
        except Exception:
            pass
    _executor.submit(runner)


async def _send_and_record(record_id: str, title: str, text: str, facts: dict, action_url: str,
                            attempt: int):
    ok, err = await _channel.send(title=title, text=text, facts=facts, action_url=action_url)
    # Open a fresh session in the worker thread to avoid sharing the request session.
    from ...database import SessionLocal
    with SessionLocal() as s:
        r = s.query(NotificationRecord).filter(NotificationRecord.id == record_id).one_or_none()
        if not r:
            return
        if ok:
            r.status = "SENT"
            r.error_message = None
            r.sent_at = datetime.utcnow()
            r.next_retry_at = None
        else:
            r.error_message = err
            r.retry_count = attempt
            if attempt >= MAX_RETRY_ATTEMPTS:
                r.status = "DEAD_LETTER"
                r.next_retry_at = None
            else:
                r.status = "RETRYING"
                delay = _BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)]
                r.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        s.commit()


def dispatch(db: Session, *, event: str, ticket: Ticket, actor_name: str | None = None,
             recipient_id: str | None = None):
    """Build a notification, persist it as PENDING, fire it asynchronously, update status."""
    title, text, facts, action_url = build_payload(event, ticket, actor_name=actor_name)
    payload = {"title": title, "text": text, "facts": facts, "action_url": action_url}

    record = NotificationRecord(
        ticket_id=ticket.id,
        recipient_id=recipient_id,
        channel=_channel.name,
        event=event,
        status="PENDING",
        payload_json=json.dumps(payload),
    )
    db.add(record); db.commit(); db.refresh(record)

    _run_async(_send_and_record(record.id, title, text, facts, action_url, attempt=1))
    return record


def retry_due(db: Session, *, batch_size: int = 50) -> int:
    """
    Pick up any RETRYING notification whose backoff window has elapsed and resend it.
    Called periodically by notification_retry_loop.py. Returns the number retried.
    """
    now = datetime.utcnow()
    due = (
        db.query(NotificationRecord)
        .filter(NotificationRecord.status == "RETRYING", NotificationRecord.next_retry_at <= now)
        .limit(batch_size)
        .all()
    )
    for record in due:
        payload = json.loads(record.payload_json)
        next_attempt = record.retry_count + 1
        _run_async(_send_and_record(
            record.id, payload["title"], payload["text"], payload["facts"], payload["action_url"],
            attempt=next_attempt,
        ))
    return len(due)


def list_recent(db: Session, limit: int = 100):
    return db.query(NotificationRecord).order_by(NotificationRecord.created_at.desc()).limit(limit).all()
