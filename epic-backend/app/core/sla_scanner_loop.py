"""
Starts the periodic SLA scan as a daemon thread, in the same style as
_run_async()'s threading.Thread in modules/notifications/service.py.

Deliberately NOT a singleton scheduler: every app instance behind the load
balancer runs its own copy of this loop. That's safe (see sla_scanner._claim)
and actually gives you redundancy — if one instance is down, the others still
catch breaches — rather than the single-point-of-failure you'd get from a
"only one instance may run this" scheduler.

Drop this file at: app/core/sla_scanner_loop.py
"""
import logging
import threading

from ..database import SessionLocal
from .sla_scanner import scan_and_escalate
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
    interval = settings.SLA_SCAN_INTERVAL_SECONDS
    logger.info(f"SLA scan loop starting, interval={interval}s")
    while not _stop.is_set():
        try:
            with SessionLocal() as db:
                scan_and_escalate(db)
        except Exception:
            logger.exception("SLA scan iteration failed, will retry next interval")
        # Returns as soon as stop() is called, instead of always blocking for the
        # full interval — this is what lets stop_background_loop() below return
        # promptly rather than waiting out whatever's left of e.g. a 5-minute sleep.
        _stop.wait(interval)
    logger.info("SLA scan loop stopped")


def start_background_loop():
    global _thread
    settings = get_settings()
    if not settings.SLA_SCAN_ENABLED:
        logger.info("SLA scan loop disabled via SLA_SCAN_ENABLED=False")
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="sla-scanner")
    _thread.start()


def stop_background_loop(timeout: float = 5.0) -> None:
    """
    Signal the loop to exit and wait (briefly) for it to actually stop.

    FIX: previously this thread was started as daemon=True with no stop signal
    and nothing in main.py ever tried to stop it — on a graceful shutdown
    (e.g. SIGTERM from an orchestrator during a rolling deploy) the process
    could exit with the thread mid-scan rather than letting it finish its
    current unit of work first. The thread stays daemon=True as a safety net
    (it will never block process exit outright even if this is never called
    or the join times out), but wiring this into FastAPI's shutdown event
    (see main.py) now gives it a real, bounded chance to stop cleanly first.
    """
    _stop.set()
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=timeout)