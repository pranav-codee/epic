"""
Notification dispatcher. Records every delivery attempt in `notification_records`
so failed Teams deliveries are observable but never block ticket actions (NFR-5.4-2).
"""
import json, asyncio, threading
from datetime import datetime
from sqlalchemy.orm import Session

from .models import NotificationRecord
from .channels.teams import TeamsChannel
from .templates import build as build_payload
from ..tickets.models import Ticket


_channel = TeamsChannel()


def _run_async(coro):
    """Run an async coroutine from a sync context without blocking the request thread."""
    def runner():
        try:
            asyncio.run(coro)
        except Exception:
            pass
    threading.Thread(target=runner, daemon=True).start()


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
    record_id = record.id

    async def _send_and_update():
        ok, err = await _channel.send(title=title, text=text, facts=facts, action_url=action_url)
        # Open a fresh session in the background thread to avoid sharing the request session.
        from ...database import SessionLocal
        with SessionLocal() as s:
            r = s.query(NotificationRecord).filter(NotificationRecord.id == record_id).one_or_none()
            if r:
                r.status = "SENT" if ok else "FAILED"
                r.error_message = err
                r.sent_at = datetime.utcnow() if ok else None
                s.commit()

    _run_async(_send_and_update())
    return record


def list_recent(db: Session, limit: int = 100):
    return db.query(NotificationRecord).order_by(NotificationRecord.created_at.desc()).limit(limit).all()
