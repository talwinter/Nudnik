"""Does this actually work?

The app measures itself. A reminder that reliably takes nine nags and four
snoozes before it closes is not a reminder problem, it is a design problem --
the task is too vague, scheduled at the wrong time, or missing the errand that
has to happen first. Surfacing that is more useful than nagging harder.
"""
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import NotificationLog, Occurrence, Reminder, utcnow

# Above this many attempts-to-close, a reminder is treated as not working.
FRICTION_ATTEMPTS = 4
FRICTION_SNOOZES = 2


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def overview(db: Session, days: int = 90) -> dict:
    since = utcnow() - timedelta(days=days)
    closed = (
        db.query(Occurrence)
        .filter(Occurrence.done_at.isnot(None), Occurrence.done_at >= since)
        .all()
    )
    done = [o for o in closed if o.status == "done"]
    skipped = [o for o in closed if o.status == "skipped"]
    missed = (
        db.query(Occurrence)
        .filter(Occurrence.status == "missed", Occurrence.due_at >= since)
        .count()
    )
    open_now = (
        db.query(Occurrence)
        .filter(Occurrence.status.in_(("active", "snoozed")))
        .count()
    )
    overdue_now = (
        db.query(Occurrence)
        .filter(Occurrence.status.in_(("active", "snoozed")), Occurrence.due_at < utcnow())
        .count()
    )

    delays = [
        (o.done_at - o.due_at).total_seconds() / 3600
        for o in done
        if o.done_at and o.due_at
    ]
    total_closed = len(done) + len(skipped) + missed

    return {
        "window_days": days,
        "done": len(done),
        "skipped": len(skipped),
        "missed": missed,
        "open_now": open_now,
        "overdue_now": overdue_now,
        "completion_rate": round(len(done) / total_closed * 100, 1) if total_closed else 0.0,
        "avg_attempts_to_close": _avg([float(o.attempts or 0) for o in done]),
        "avg_hours_late": _avg([d for d in delays if d >= 0]),
        "first_nudge_success": round(
            sum(1 for o in done if (o.attempts or 0) <= 1) / len(done) * 100, 1
        )
        if done
        else 0.0,
        "total_snoozes": int(
            db.query(func.coalesce(func.sum(Occurrence.snooze_count), 0)).scalar() or 0
        ),
    }


def channel_effectiveness(db: Session, days: int = 90) -> list[dict]:
    """Which channel was the last one to fire before you acted.

    Attribution is approximate -- you may have seen three and acted on one --
    but over enough closes the ranking is informative, and it is the only
    honest way to answer "is email doing anything for me?".
    """
    since = utcnow() - timedelta(days=days)
    done = (
        db.query(Occurrence)
        .filter(Occurrence.status == "done", Occurrence.done_at >= since)
        .all()
    )

    credit: dict[str, int] = {}
    sent: dict[str, int] = {}

    for occ in done:
        logs = [
            log
            for log in occ.logs
            if log.status == "ok" and occ.done_at and log.created_at <= occ.done_at
        ]
        for log in logs:
            sent[log.channel] = sent.get(log.channel, 0) + 1
        if logs:
            last = max(logs, key=lambda log: log.created_at)
            credit[last.channel] = credit.get(last.channel, 0) + 1

    # Include channels that fired but never preceded a close.
    all_sent = (
        db.query(NotificationLog.channel, func.count(NotificationLog.id))
        .filter(NotificationLog.status == "ok", NotificationLog.created_at >= since)
        .group_by(NotificationLog.channel)
        .all()
    )
    totals = {channel: count for channel, count in all_sent}

    rows = []
    for channel, total in sorted(totals.items(), key=lambda kv: -kv[1]):
        closes = credit.get(channel, 0)
        rows.append(
            {
                "channel": channel,
                "sent": total,
                "closes_credited": closes,
                "conversion": round(closes / total * 100, 1) if total else 0.0,
            }
        )
    return rows


def problem_reminders(db: Session, limit: int = 10) -> list[dict]:
    """Reminders that consistently need chasing, with a concrete suggestion."""
    rows = []
    reminders = db.query(Reminder).filter(Reminder.active.is_(True)).all()

    for rem in reminders:
        closed = [o for o in rem.occurrences if o.status in ("done", "skipped", "missed")]
        if not closed:
            continue
        done = [o for o in closed if o.status == "done"]
        attempts = _avg([float(o.attempts or 0) for o in closed])
        snoozes = _avg([float(o.snooze_count or 0) for o in closed])
        misses = sum(1 for o in closed if o.status == "missed")
        lateness = _avg(
            [
                (o.done_at - o.due_at).total_seconds() / 3600
                for o in done
                if o.done_at and o.due_at and o.done_at > o.due_at
            ]
        )

        score = attempts + snoozes * 2 + misses * 3
        if score < FRICTION_ATTEMPTS:
            continue

        rows.append(
            {
                "reminder_id": rem.id,
                "title": rem.title,
                "emoji": rem.emoji,
                "avg_attempts": attempts,
                "avg_snoozes": snoozes,
                "missed": misses,
                "avg_hours_late": lateness,
                "score": round(score, 1),
                "suggestion": _suggest(rem, attempts, snoozes, misses, lateness),
            }
        )

    rows.sort(key=lambda r: -r["score"])
    return rows[:limit]


def _suggest(rem: Reminder, attempts: float, snoozes: float, misses: int, lateness: float) -> dict:
    """A specific, actionable fix -- never generic advice."""
    stages = rem.stages or []
    has_prep = any((s or {}).get("offset_minutes", 0) < 0 for s in stages)

    if snoozes >= FRICTION_SNOOZES and lateness > 12:
        return {
            "code": "wrong_time",
            "he": "אתה דוחה את זה שוב ושוב — כנראה השעה לא מתאימה. נסה להזיז את התזכורת לשעה שבה אתה באמת פנוי לטפל בזה.",
            "en": "You snooze this repeatedly, which usually means the time is wrong. Move it to an hour when you can actually act.",
        }
    if not has_prep and attempts >= FRICTION_ATTEMPTS:
        return {
            "code": "needs_prep",
            "he": "המשימה כנראה דורשת צעד מקדים. הוסף שלב הכנה כמה ימים לפני — לרוב אי אפשר לבצע את זה ברגע שהתזכורת מגיעה.",
            "en": "This probably needs a prior errand. Add a prep stage a few days earlier — it likely cannot be done the moment the reminder lands.",
        }
    if misses >= 2:
        return {
            "code": "escalate",
            "he": "זה נופל בין הכיסאות. העלה את העצימות ל\"נודניק\" והפעל התראה לאיש קשר.",
            "en": "This keeps falling through. Raise intensity to relentless and turn on the accountability contact.",
        }
    if rem.contact_phone is None and attempts >= FRICTION_ATTEMPTS:
        return {
            "code": "add_contact",
            "he": "הוסף מספר טלפון לתזכורת — כשיש כפתור חיוג ישיר בהתראה, הרבה יותר קל פשוט לעשות את זה.",
            "en": "Add a phone number. A call button inside the notification removes the step that gets this postponed.",
        }
    return {
        "code": "split",
        "he": "המשימה כנראה גדולה מדי לתזכורת אחת. פצל אותה לשני שלבים קטנים יותר.",
        "en": "This is probably too big for one reminder. Split it into two smaller stages.",
    }


def activity_series(db: Session, days: int = 30) -> list[dict]:
    """Daily counts for the dashboard sparkline."""
    since = utcnow() - timedelta(days=days)
    out: dict[str, dict] = {}
    for i in range(days + 1):
        day = (since + timedelta(days=i)).date().isoformat()
        out[day] = {"date": day, "done": 0, "created": 0, "missed": 0}

    for occ in db.query(Occurrence).filter(Occurrence.done_at >= since).all():
        key = occ.done_at.date().isoformat()
        if key in out and occ.status == "done":
            out[key]["done"] += 1

    for occ in db.query(Occurrence).filter(Occurrence.created_at >= since).all():
        key = occ.created_at.date().isoformat()
        if key in out:
            out[key]["created"] += 1

    for occ in (
        db.query(Occurrence)
        .filter(Occurrence.status == "missed", Occurrence.due_at >= since)
        .all()
    ):
        key = occ.due_at.date().isoformat()
        if key in out:
            out[key]["missed"] += 1

    return list(out.values())
