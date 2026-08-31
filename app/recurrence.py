"""Turning reminder definitions into concrete open loops.

Materialisation is idempotent: it is safe to run every hour, and it will never
create a duplicate for a ``(reminder, cycle, stage)`` triple that already
exists.
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from .config import GIVE_UP_DAYS, HORIZON_DAYS
from .db import Occurrence, Reminder, utcnow

MAX_CYCLES = 400

OPEN_STATUSES = ("scheduled", "active", "snoozed")
CLOSED_STATUSES = ("done", "skipped", "missed", "cancelled")


_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def apply_stage_time(due_utc: datetime, hhmm: str | None, tzname: str | None) -> datetime:
    """Pin an occurrence to a specific local time of day.

    Stages inherit the event's time by default, which is wrong for most of
    them: an injection at 19:00 is fine, but the pharmacy call two weeks
    earlier has to land in business hours. The stage time is wall-clock local,
    so it is applied in the reminder's timezone and converted back to UTC --
    otherwise it would drift by an hour across a DST boundary.
    """
    if not hhmm or not _HHMM.match(str(hhmm).strip()):
        return due_utc
    try:
        tz = ZoneInfo(tzname or "UTC")
    except Exception:  # noqa: BLE001 - an unknown tz must not lose the stage
        return due_utc
    hour, minute = (int(x) for x in str(hhmm).strip().split(":"))
    local = due_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    local = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def advance(base: datetime, kind: str, steps: int) -> datetime:
    """Move ``base`` forward by ``steps`` repetitions of ``kind``."""
    if steps == 0:
        return base
    if kind == "daily":
        return base + timedelta(days=steps)
    if kind == "weekly":
        return base + timedelta(weeks=steps)
    if kind == "monthly":
        return base + relativedelta(months=steps)
    if kind == "yearly":
        return base + relativedelta(years=steps)
    if kind == "hourly":
        return base + timedelta(hours=steps)
    return base


def offset_local(base_utc: datetime, minutes: int, tzname: str | None) -> datetime:
    """Apply a stage offset in wall-clock terms.

    "14 days before" should land at the same time of day as the event, but
    adding 14 days of UTC across a daylight-saving change shifts it by an hour.
    """
    if not minutes:
        return base_utc
    try:
        tz = ZoneInfo(tzname or "UTC")
    except Exception:  # noqa: BLE001
        return base_utc + timedelta(minutes=minutes)
    local = base_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).replace(tzinfo=None)
    moved = local + timedelta(minutes=minutes)
    return moved.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def advance_local(base_utc: datetime, kind: str, steps: int, tzname: str | None) -> datetime:
    """Advance a recurrence in *wall-clock* terms, not UTC terms.

    "Every 8 weeks at 19:00" means 19:00 on the clock. Doing the arithmetic in
    UTC preserves the UTC hour instead, so a cycle crossing a daylight-saving
    boundary silently shifts to 18:00 (or 20:00) local and stays there.
    """
    if steps == 0:
        return base_utc
    try:
        tz = ZoneInfo(tzname or "UTC")
    except Exception:  # noqa: BLE001 - unknown tz: fall back to plain UTC maths
        return advance(base_utc, kind, steps)
    local = base_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).replace(tzinfo=None)
    moved = advance(local, kind, steps)
    return moved.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _weekly_anchors(rem: Reminder, horizon_end: datetime):
    """Weekly reminders with explicit weekdays, e.g. Sun/Tue/Thu."""
    days = sorted({int(x) for x in (rem.repeat_weekdays or "").split(",") if x.strip() != ""})
    if not days:
        return
    base = rem.anchor_at
    interval = max(1, rem.repeat_interval or 1)
    cycle = 0
    week = 0
    while cycle < MAX_CYCLES and week < MAX_CYCLES:
        week_start = advance_local(base, "weekly", week * interval, rem.tz)
        monday = week_start - timedelta(days=week_start.weekday())
        for d in days:
            dt = (monday + timedelta(days=d)).replace(
                hour=base.hour, minute=base.minute, second=0, microsecond=0
            )
            if dt < base:
                continue
            if dt > horizon_end:
                return
            yield cycle, dt
            cycle += 1
            if rem.repeat_count and cycle >= rem.repeat_count:
                return
        week += 1


def iter_anchors(rem: Reminder, horizon_end: datetime):
    """Yield ``(cycle, anchor_datetime)`` pairs up to the horizon."""
    kind = (rem.repeat_kind or "none").lower()

    if kind in ("none", "", "once"):
        yield 0, rem.anchor_at
        return

    # Completion-anchored cycles cannot be predicted ahead of time; the next
    # one is created when the current cycle is actually closed.
    if rem.anchor_to_completion:
        yield rem.cycles_done or 0, rem.anchor_at
        return

    if kind == "weekly" and rem.repeat_weekdays:
        yield from _weekly_anchors(rem, horizon_end)
        return

    interval = max(1, rem.repeat_interval or 1)
    cycle = 0
    while cycle < MAX_CYCLES:
        dt = advance_local(rem.anchor_at, kind, interval * cycle, rem.tz)
        if dt > horizon_end:
            return
        if rem.repeat_until and dt > rem.repeat_until:
            return
        yield cycle, dt
        cycle += 1
        if rem.repeat_count and cycle >= rem.repeat_count:
            return


def normalise_stages(stages) -> list[dict]:
    """Always guarantee a stage at offset 0 -- the event itself."""
    cleaned: list[dict] = []
    for st in stages or []:
        try:
            offset = int(st.get("offset_minutes", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        entry = {
            "offset_minutes": offset,
            "label": (st.get("label") or "").strip(),
            "kind": st.get("kind") or ("main" if offset == 0 else "prep"),
        }
        # Optional per-stage override. An informational stage ("the date is
        # approaching") should not be chased as hard as the errand that has to
        # happen. Absent means: inherit the reminder's intensity.
        intensity = st.get("intensity")
        if intensity in ("gentle", "normal", "relentless"):
            entry["intensity"] = intensity
        # Optional local wall-clock time for this stage. Absent means: inherit
        # the event's time of day.
        at_time = (st.get("at_time") or "").strip()
        if _HHMM.match(at_time):
            entry["at_time"] = at_time
        cleaned.append(entry)
    if not any(s["offset_minutes"] == 0 for s in cleaned):
        cleaned.append({"offset_minutes": 0, "label": "", "kind": "main"})
    cleaned.sort(key=lambda s: s["offset_minutes"])
    return cleaned


def materialise(db: Session, rem: Reminder, now: datetime | None = None) -> int:
    """Create any missing occurrences for one reminder. Returns how many."""
    now = now or utcnow()
    horizon_end = now + timedelta(days=HORIZON_DAYS)
    give_up_before = now - timedelta(days=GIVE_UP_DAYS)

    if not rem.active or rem.archived_at:
        return 0

    stages = normalise_stages(rem.stages)
    existing = {
        (o.cycle, o.stage_index)
        for o in db.query(Occurrence.cycle, Occurrence.stage_index)
        .filter(Occurrence.reminder_id == rem.id)
        .all()
    }

    created = 0
    for cycle, anchor in iter_anchors(rem, horizon_end):
        for idx, stage in enumerate(stages):
            if (cycle, idx) in existing:
                continue
            due = offset_local(anchor, stage["offset_minutes"], rem.tz)
            due = apply_stage_time(due, stage.get("at_time"), rem.tz)

            # A lead-time stage already in the past still matters: add a
            # reminder today for a medicine due next week and the "order it"
            # step should nag immediately rather than be silently dropped.
            if due < give_up_before:
                continue

            db.add(
                Occurrence(
                    reminder_id=rem.id,
                    cycle=cycle,
                    stage_index=idx,
                    stage_label=stage["label"],
                    stage_kind=stage["kind"],
                    due_at=due,
                    status="scheduled",
                    next_attempt_at=due,
                )
            )
            created += 1
    if created:
        db.flush()
    return created


def spawn_next_cycle(db: Session, rem: Reminder, completed_at: datetime) -> int:
    """For completion-anchored reminders, schedule the next round.

    Called when the ``main`` stage of the current cycle is marked done.
    """
    if not rem.anchor_to_completion:
        return 0
    kind = (rem.repeat_kind or "none").lower()
    if kind in ("none", "", "once"):
        return 0

    interval = max(1, rem.repeat_interval or 1)
    next_anchor = advance_local(completed_at, kind, interval, rem.tz)
    # Keep the original time of day rather than inheriting the moment you
    # happened to tap "done" -- and keep it as a *wall-clock* time. Copying the
    # stored UTC hour instead would reintroduce the daylight-saving drift that
    # advance_local just avoided.
    try:
        tz = ZoneInfo(rem.tz or "UTC")
        original_local = rem.anchor_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        next_anchor = apply_stage_time(
            next_anchor, f"{original_local.hour:02d}:{original_local.minute:02d}", rem.tz
        )
    except Exception:  # noqa: BLE001 - never lose the cycle over a bad tz
        next_anchor = next_anchor.replace(
            hour=rem.anchor_at.hour, minute=rem.anchor_at.minute, second=0, microsecond=0
        )

    if rem.repeat_until and next_anchor > rem.repeat_until:
        return 0
    rem.cycles_done = (rem.cycles_done or 0) + 1
    if rem.repeat_count and rem.cycles_done >= rem.repeat_count:
        return 0

    rem.anchor_at = next_anchor
    stages = normalise_stages(rem.stages)
    cycle = rem.cycles_done
    created = 0
    for idx, stage in enumerate(stages):
        due = offset_local(next_anchor, stage["offset_minutes"], rem.tz)
        due = apply_stage_time(due, stage.get("at_time"), rem.tz)
        db.add(
            Occurrence(
                reminder_id=rem.id,
                cycle=cycle,
                stage_index=idx,
                stage_label=stage["label"],
                stage_kind=stage["kind"],
                due_at=due,
                status="scheduled",
                next_attempt_at=due,
            )
        )
        created += 1
    db.flush()
    return created


def materialise_all(db: Session) -> int:
    total = 0
    for rem in db.query(Reminder).filter(Reminder.active.is_(True)).all():
        total += materialise(db, rem)
    if total:
        db.commit()
    return total


def resync(db: Session, rem: Reminder) -> None:
    """Rebuild future open occurrences after a reminder is edited.

    Closed occurrences and anything already being chased are preserved, so
    editing a reminder never erases history or drops an active nag.
    """
    now = utcnow()
    (
        db.query(Occurrence)
        .filter(
            Occurrence.reminder_id == rem.id,
            Occurrence.status == "scheduled",
            Occurrence.due_at > now,
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    materialise(db, rem, now)
