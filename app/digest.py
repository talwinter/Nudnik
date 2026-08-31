"""Daily and weekly briefs.

Interrupt-driven reminding has a blind spot: things you already dismissed drop
out of sight. The brief is the counterweight -- one scheduled moment where
everything still open is listed together, whether or not it nagged you today.
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from . import channels, settings_store
from .db import Occurrence, Reminder, log_event, utcnow
from .engine import to_local
from .i18n import humanise_delta, t


def _line(db: Session, occ: Occurrence, lang: str) -> str:
    rem = occ.reminder
    label = occ.stage_label or (rem.title if rem else "")
    emoji = (rem.emoji + " ") if rem and rem.emoji else "• "
    local = to_local(db, occ.due_at)
    when = local.strftime("%d/%m %H:%M")
    if (occ.attempts or 0) > 2:
        return f"{emoji}{label} — {when} ({t('asked_times', lang, n=occ.attempts)})"
    return f"{emoji}{label} — {when}"


def collect(db: Session, days_ahead: int = 7) -> dict:
    now = utcnow()
    horizon = now + timedelta(days=days_ahead)
    end_of_today = (
        to_local(db, now).replace(hour=23, minute=59, second=59)
    )
    end_of_today_utc = end_of_today.astimezone(to_local(db, now).tzinfo).replace(tzinfo=None)

    open_occ = (
        db.query(Occurrence)
        .join(Reminder, Occurrence.reminder_id == Reminder.id)
        .filter(
            Occurrence.status.in_(("active", "snoozed", "scheduled")),
            Reminder.active.is_(True),
            Occurrence.due_at <= horizon,
        )
        .order_by(Occurrence.due_at)
        .all()
    )

    overdue = [o for o in open_occ if o.due_at < now]
    today = [
        o for o in open_occ if now <= o.due_at <= end_of_today_utc + timedelta(hours=0)
    ]
    soon = [o for o in open_occ if o.due_at > end_of_today_utc]
    return {"overdue": overdue, "today": today, "soon": soon, "all": open_occ}


def send_daily_brief(db: Session) -> dict:
    lang = settings_store.get(db, "lang", "he")
    data = collect(db, days_ahead=7)

    if not data["all"]:
        body = t("brief_empty", lang)
    else:
        sections = []
        if data["overdue"]:
            sections.append(
                f"⚠️ {t('brief_overdue', lang)}\n"
                + "\n".join(_line(db, o, lang) for o in data["overdue"][:12])
            )
        if data["today"]:
            sections.append(
                f"📅 {t('brief_today', lang)}\n"
                + "\n".join(_line(db, o, lang) for o in data["today"][:12])
            )
        if data["soon"]:
            sections.append(
                f"🔜 {t('brief_soon', lang)}\n"
                + "\n".join(_line(db, o, lang) for o in data["soon"][:10])
            )
        body = "\n\n".join(sections)

    base = settings_store.get(db, "public_url", "").rstrip("/")
    msg = channels.Message(
        title=f"{t('brief_title', lang)} · {len(data['overdue'])}⚠",
        body=body,
        tier=1,
        links={"open": base or "/"},
        lang=lang,
    )

    results = {}
    for channel in ("push", "ntfy", "telegram", "email"):
        ok, detail = channels.dispatch(db, channel, msg, ntfy_priority=3)
        results[channel] = {"ok": ok, "detail": detail}

    log_event(
        db,
        "brief",
        f"Daily brief: {len(data['overdue'])} overdue, {len(data['today'])} today",
        {"results": {k: v["ok"] for k, v in results.items()}},
    )
    db.commit()
    return {"counts": {k: len(v) for k, v in data.items()}, "results": results}


def send_weekly_brief(db: Session) -> dict:
    lang = settings_store.get(db, "lang", "he")
    data = collect(db, days_ahead=14)
    lines = [_line(db, o, lang) for o in data["all"][:25]]
    body = "\n".join(lines) if lines else t("brief_empty", lang)

    base = settings_store.get(db, "public_url", "").rstrip("/")
    msg = channels.Message(
        title=t("weekly_title", lang),
        body=body,
        tier=1,
        links={"open": base or "/"},
        lang=lang,
    )
    results = {}
    for channel in ("ntfy", "telegram", "email"):
        ok, detail = channels.dispatch(db, channel, msg, ntfy_priority=3)
        results[channel] = {"ok": ok, "detail": detail}
    log_event(db, "brief", "Weekly brief", {"count": len(data["all"])})
    db.commit()
    return {"count": len(data["all"]), "results": results}


def preview(db: Session) -> dict:
    """What the brief would say right now, for the admin UI."""
    lang = settings_store.get(db, "lang", "he")
    data = collect(db, days_ahead=7)
    return {
        "overdue": [_line(db, o, lang) for o in data["overdue"]],
        "today": [_line(db, o, lang) for o in data["today"]],
        "soon": [_line(db, o, lang) for o in data["soon"]],
    }
