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
import time

from ..database import SessionLocal
from .sla_scanner import scan_and_escalate
from ..config import get_settings

logger = logging.getLogger(__name__)


def _loop():
    settings = get_settings()
    interval = settings.SLA_SCAN_INTERVAL_SECONDS
    logger.info(f"SLA scan loop starting, interval={interval}s")
    while True:
        try:
            with SessionLocal() as db:
                scan_and_escalate(db)
        except Exception:
            logger.exception("SLA scan iteration failed, will retry next interval")
        time.sleep(interval)


def start_background_loop():
    settings = get_settings()
    if not settings.SLA_SCAN_ENABLED:
        logger.info("SLA scan loop disabled via SLA_SCAN_ENABLED=False")
        return
    threading.Thread(target=_loop, daemon=True, name="sla-scanner").start()