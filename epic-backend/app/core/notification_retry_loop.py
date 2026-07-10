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

from ..database import SessionLocal
from ..modules.notifications.service import retry_due
from ..config import get_settings

logger = logging.getLogger(__name__)

# Sweep more often than the SLA scanner — backoff windows start at 30s, so a
# slow sweep interval would just add dead time on top of the intended delay.
RETRY_SWEEP_INTERVAL_SECONDS = 30

# Signals the loop to exit. Checked between iterations and used (instead of
# time.sleep) to wait out the interval, so a shutdown request interrupts a
# pending sleep immediately rather than waiting out however much of the
# interval is left.
_stop = threading.Event()
_thread: threading.Thread | None = None


def _loop():
    logger.info(f"Notification retry loop starting, interval={RETRY_SWEEP_INTERVAL_SECONDS}s")
    while not _stop.is_set():
        try:
            with SessionLocal() as db:
                n = retry_due(db)
                if n:
                    logger.info(f"Notification retry sweep: resent {n} due notification(s)")
        except Exception:
            logger.exception("Notification retry sweep failed, will retry next interval")
        # Returns as soon as stop() is called, instead of always blocking for the
        # full interval — this is what lets stop_background_loop() below return
        # promptly rather than waiting out whatever's left of the 30s sweep.
        _stop.wait(RETRY_SWEEP_INTERVAL_SECONDS)
    logger.info("Notification retry loop stopped")


def start_background_loop():
    global _thread
    settings = get_settings()
    if not settings.TEAMS_NOTIFICATIONS_ENABLED:
        logger.info("Notification retry loop disabled via TEAMS_NOTIFICATIONS_ENABLED=False")
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="notification-retry")
    _thread.start()


def stop_background_loop(timeout: float = 5.0) -> None:
    """
    Signal the loop to exit and wait (briefly) for it to actually stop.

    FIX: previously this thread was started as daemon=True with no stop signal
    and nothing in main.py ever tried to stop it — on a graceful shutdown the
    process could exit with the thread mid-sweep rather than letting it finish
    its current unit of work first. Stays daemon=True as a safety net (it will
    never block process exit outright even if this is never called or the join
    times out), but wiring this into FastAPI's shutdown event (see main.py) now
    gives it a real, bounded chance to stop cleanly first.
    """
    _stop.set()
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=timeout)