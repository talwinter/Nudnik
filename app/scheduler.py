"""Background jobs.

The tick is also exposed as an HTTP endpoint, so the same engine runs whether
it is driven from inside the process (a VPS that is always on) or poked from
outside by a cron pinger (a free host that sleeps). Both paths call
``engine.tick`` and both are safe to run concurrently -- worst case a rung is
attempted a few seconds early.
"""
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import digest, settings_store
from .config import SCHEDULER_ENABLED, TICK_SECONDS
from .db import SessionLocal
from .engine import tick
from .recurrence import materialise_all

log = logging.getLogger("nudnik.scheduler")
scheduler = BackgroundScheduler(timezone="UTC")


def _session_job(fn, name: str):
    def wrapper():
        db = SessionLocal()
        try:
            result = fn(db)
            if result:
                log.info("%s: %s", name, result)
        except Exception:  # noqa: BLE001 - a failing job must not kill the loop
            log.exception("%s failed", name)
            db.rollback()
        finally:
            db.close()

    return wrapper


def run_tick() -> dict:
    db = SessionLocal()
    try:
        return tick(db)
    finally:
        db.close()


def _brief_job(kind: str):
    def wrapper():
        db = SessionLocal()
        try:
            if kind == "daily":
                if settings_store.get(db, "brief_enabled", True):
                    if _is_brief_time(db, "brief_time"):
                        digest.send_daily_brief(db)
            else:
                if settings_store.get(db, "weekly_brief_enabled", True):
                    weekday = int(settings_store.get(db, "weekly_brief_weekday", 6) or 6)
                    from .engine import to_local
                    from .db import utcnow

                    local = to_local(db, utcnow())
                    if local.weekday() == weekday and _is_brief_time(db, "brief_time"):
                        digest.send_weekly_brief(db)
        except Exception:  # noqa: BLE001
            log.exception("%s brief failed", kind)
            db.rollback()
        finally:
            db.close()

    return wrapper


def _is_brief_time(db, key: str) -> bool:
    """True within the five-minute window after the configured brief time.

    Checked in local time on every run so changing the setting takes effect
    without rescheduling the job.
    """
    from .db import utcnow
    from .engine import to_local

    raw = settings_store.get(db, key, "08:30")
    try:
        hh, mm = str(raw).split(":")
        target = int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        target = 8 * 60 + 30
    local = to_local(db, utcnow())
    minutes = local.hour * 60 + local.minute
    return 0 <= (minutes - target) < 5


def start() -> None:
    if not SCHEDULER_ENABLED:
        log.info("Internal scheduler disabled; drive POST /api/tick externally")
        return

    scheduler.add_job(
        _session_job(tick, "tick"),
        IntervalTrigger(seconds=TICK_SECONDS),
        id="tick",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _session_job(lambda db: materialise_all(db), "materialise"),
        IntervalTrigger(minutes=30),
        id="materialise",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _brief_job("daily"),
        IntervalTrigger(minutes=5),
        id="daily_brief",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _brief_job("weekly"),
        IntervalTrigger(minutes=5),
        id="weekly_brief",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        _session_job(_prune, "prune"),
        CronTrigger(hour=3, minute=0),
        id="prune",
        replace_existing=True,
    )
    scheduler.start()
    log.info("Scheduler started, ticking every %ss", TICK_SECONDS)


def _prune(db) -> str:
    """Housekeeping: drop spent tokens and very old delivery logs."""
    from datetime import timedelta

    from .db import ActionToken, Event, NotificationLog, utcnow

    now = utcnow()
    tokens = (
        db.query(ActionToken)
        .filter(ActionToken.expires_at < now)
        .delete(synchronize_session=False)
    )
    logs = (
        db.query(NotificationLog)
        .filter(NotificationLog.created_at < now - timedelta(days=180))
        .delete(synchronize_session=False)
    )
    events = (
        db.query(Event)
        .filter(Event.created_at < now - timedelta(days=365))
        .delete(synchronize_session=False)
    )
    db.commit()
    return f"pruned {tokens} tokens, {logs} logs, {events} events"


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def status() -> dict:
    return {
        "enabled": SCHEDULER_ENABLED,
        "running": scheduler.running if SCHEDULER_ENABLED else False,
        "tick_seconds": TICK_SECONDS,
        "jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in (scheduler.get_jobs() if scheduler.running else [])
        ],
        "server_time_utc": datetime.utcnow().isoformat() + "Z",
    }
