"""
Starts a periodic sweep for notifications stuck in RETRYING, in the same style
as sla_scanner_loop.py.

Fixes: previously a failed Teams delivery (webhook down, network blip, 429, etc.)
was marked FAILED once and never looked at again. Now failed sends move to
RETRYING with a next_retry_at (see notifications/service.py's backoff schedule),
and this loop is what actually picks them back up and resends them.

Deliberately NOT a singleton scheduler, for the same reason as the SLA scanner:
every app instance runs its own copy. Two instances racing on the same due
record just both call retry_due(), which is idempotent enough here since the
worst case is one duplicate Teams message on a rare race — the same tradeoff
already accepted for the original send path. If that becomes a real duplicate-
notification problem in practice, apply the same atomic-claim UPDATE pattern
used in sla_scanner.py's _claim().

Drop this file at: app/core/notification_retry_loop.py
"""
import logging
import threading
import time

from ..database import SessionLocal
from ..modules.notifications.service import retry_due
from ..config import get_settings

logger = logging.getLogger(__name__)

# Sweep more often than the SLA scanner — backoff windows start at 30s, so a
# slow sweep interval would just add dead time on top of the intended delay.
RETRY_SWEEP_INTERVAL_SECONDS = 30


def _loop():
    logger.info(f"Notification retry loop starting, interval={RETRY_SWEEP_INTERVAL_SECONDS}s")
    while True:
        try:
            with SessionLocal() as db:
                n = retry_due(db)
                if n:
                    logger.info(f"Notification retry sweep: resent {n} due notification(s)")
        except Exception:
            logger.exception("Notification retry sweep failed, will retry next interval")
        time.sleep(RETRY_SWEEP_INTERVAL_SECONDS)


def start_background_loop():
    settings = get_settings()
    if not settings.TEAMS_NOTIFICATIONS_ENABLED:
        logger.info("Notification retry loop disabled via TEAMS_NOTIFICATIONS_ENABLED=False")
        return
    threading.Thread(target=_loop, daemon=True, name="notification-retry").start()
