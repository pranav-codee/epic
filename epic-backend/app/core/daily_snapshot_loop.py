"""
Starts the periodic open-ticket-by-group snapshot as a daemon thread, in the same style
as sla_scanner_loop.py (which in turn follows _run_async()'s threading.Thread in
modules/notifications/service.py).

Deliberately NOT a singleton scheduler: every app instance behind the load balancer runs
its own copy of this loop, same tradeoff as sla_scanner_loop.py. That's safe here too —
reporting/service.py's take_daily_snapshot() deletes-then-reinserts all rows for a given
snapshot_date in one transaction, so two instances both firing on the same day just both
write the same end state rather than producing duplicate/conflicting rows.

Drop this file at: app/core/daily_snapshot_loop.py
"""
import logging
import threading

from ..database import SessionLocal
from ..modules.reporting.service import take_daily_snapshot
from ..config import get_settings

logger = logging.getLogger(__name__)

# Signals the loop to exit. Checked between iterations and used (instead of
# time.sleep) to wait out the interval, so a shutdown request interrupts a
# pending sleep immediately rather than waiting out however much of the
# interval is left.
_stop = threading.Event()
_thread: threading.Thread | None = None


def _loop():
    settings = get_settings()
    interval = settings.DAILY_SNAPSHOT_INTERVAL_SECONDS
    logger.info(f"Daily group snapshot loop starting, interval={interval}s")
    while not _stop.is_set():
        try:
            with SessionLocal() as db:
                take_daily_snapshot(db)
        except Exception:
            logger.exception("Daily group snapshot iteration failed, will retry next interval")
        # Returns as soon as stop() is called, instead of always blocking for the
        # full interval — this is what lets stop_background_loop() below return
        # promptly rather than waiting out whatever's left of e.g. a 24-hour sleep.
        _stop.wait(interval)
    logger.info("Daily group snapshot loop stopped")


def start_background_loop():
    global _thread
    settings = get_settings()
    if not settings.DAILY_SNAPSHOT_ENABLED:
        logger.info("Daily group snapshot loop disabled via DAILY_SNAPSHOT_ENABLED=False")
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="daily-group-snapshot")
    _thread.start()


def stop_background_loop(timeout: float = 5.0) -> None:
    """
    Signal the loop to exit and wait (briefly) for it to actually stop.

    Same shutdown-hook rationale as sla_scanner_loop.stop_background_loop(): without this,
    a graceful stop (e.g. SIGTERM during a rolling deploy) could exit the process mid-write
    instead of letting the current snapshot finish. Stays daemon=True as a safety net (it
    will never block process exit outright even if this is never called or the join times
    out), but wiring this into FastAPI's shutdown event (see main.py) gives it a real,
    bounded chance to stop cleanly first.
    """
    _stop.set()
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=timeout)