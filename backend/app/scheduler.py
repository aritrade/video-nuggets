"""
APScheduler-based scheduler for the optional periodic content monitor.

Disabled by default. Enable by setting MONITOR_ENABLED=true and pointing
MONITOR_SOURCE_URL at a docs site to watch for drift.
"""
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import MONITOR_INTERVAL_HOURS, MONITOR_ENABLED, MONITOR_SOURCE_URL

scheduler = BackgroundScheduler()


def _run_monitor():
    """Wrapper to run async monitor in sync context."""
    from app.services.content_monitor import run_content_check
    asyncio.run(run_content_check(triggered_by="scheduler"))


def start_scheduler():
    """Start the background content-monitor job, if enabled."""
    if not (MONITOR_ENABLED and MONITOR_SOURCE_URL):
        print("[Scheduler] Content monitor disabled (set MONITOR_ENABLED=true + MONITOR_SOURCE_URL to enable)")
        return
    scheduler.add_job(
        _run_monitor,
        trigger=IntervalTrigger(hours=MONITOR_INTERVAL_HOURS),
        id="content_monitor",
        name="Content Monitor",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[Scheduler] Started - checking every {MONITOR_INTERVAL_HOURS} hours")


def stop_scheduler():
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped")
