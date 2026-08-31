"""The nagging engine.

One tick does four things, in order:

1. promotes occurrences that have come due,
2. wakes snoozed occurrences whose snooze has expired,
3. sends the next rung of the ladder for anything still open,
4. retires occurrences that are so old they are no longer worth chasing.

Nothing here ever closes a loop. Only a human action does that.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import channels, escalation, settings_store
from .config import GIVE_UP_DAYS
from .db import Occurrence, Reminder, log_event, utcnow
from .i18n import humanise_delta, t
from .recurrence import spawn_next_cycle

# Serial snoozing is itself a signal. After this many snoozes the ladder stops
# resetting and the occurrence keeps its escalation tier, so "later, later,
# later" stops being a way to stay at the gentlest channel forever.
SNOOZE_PATIENCE = 3


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------


def tz_of(db: Session) -> ZoneInfo:
    try:
        return ZoneInfo(settings_store.get(db, "timezone", "Asia/Jerusalem"))
    except Exception:  # noqa: BLE001 - bad tz name must not stop the engine
        return ZoneInfo("UTC")


def to_local(db: Session, dt: datetime) -> datetime:
    return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_of(db))


def to_utc(db: Session, local_dt: datetime) -> datetime:
    return (
        local_dt.replace(tzinfo=tz_of(db)).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    )


def _parse_hhmm(value: str, fallback: time) -> time:
    try:
        hh, mm = str(value).split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return fallback


def in_quiet_hours(db: Session, when_utc: datetime) -> bool:
    if not settings_store.get(db, "quiet_hours_enabled", True):
        return False
    start = _parse_hhmm(settings_store.get(db, "quiet_start", "23:00"), time(23, 0))
    end = _parse_hhmm(settings_store.get(db, "quiet_end", "07:30"), time(7, 30))
    local = to_local(db, when_utc).time()
    if start <= end:
        return start <= local < end
    # Window crosses midnight, which is the normal case for sleep.
    return local >= start or local < end


def next_quiet_end(db: Session, when_utc: datetime) -> datetime:
    end = _parse_hhmm(settings_store.get(db, "quiet_end", "07:30"), time(7, 30))
    local = to_local(db, when_utc)
    candidate = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def resolve_snooze(db: Session, preset: str | None, minutes: int | None) -> datetime:
    """Turn a snooze request into a concrete UTC moment."""
    now = utcnow()
    if minutes:
        return now + timedelta(minutes=int(minutes))

    local = to_local(db, now)
    if preset == "evening":
        target = local.replace(hour=18, minute=0, second=0, microsecond=0)
        if target <= local:
            target += timedelta(days=1)
    elif preset == "tomorrow":
        target = (local + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
    elif preset == "weekend":
        target = local.replace(hour=10, minute=0, second=0, microsecond=0)
        # Friday is the start of the Israeli weekend.
        while target.weekday() != 4 or target <= local:
            target += timedelta(days=1)
    elif preset == "next_week":
        target = (local + timedelta(days=7)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
    else:
        return now + timedelta(hours=1)
    return target.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


# --------------------------------------------------------------------------
# Message rendering
# --------------------------------------------------------------------------


def render(db: Session, occ: Occurrence, rem: Reminder, lang: str) -> channels.Message:
    headline = occ.stage_label or rem.title
    if occ.stage_label and occ.stage_label != rem.title:
        headline = f"{occ.stage_label}"

    prefix = f"{rem.emoji} " if rem.emoji else ""
    title = f"{prefix}{headline}".strip()

    parts: list[str] = []
    if occ.stage_label and occ.stage_label != rem.title:
        parts.append(rem.title)

    overdue_minutes = int((utcnow() - occ.due_at).total_seconds() // 60)
    if overdue_minutes >= 5:
        parts.append(
            f"{t('overdue_since', lang)} {humanise_delta(overdue_minutes, lang)}"
        )
    elif overdue_minutes >= -1:
        parts.append(t("due_now", lang))

    attempts = occ.attempts or 0
    if attempts >= 1:
        parts.append(t("asked_times", lang, n=attempts + 1))

    if rem.notes:
        parts.append(rem.notes)

    return channels.Message(
        title=title,
        body="\n".join(p for p in parts if p),
        occurrence_id=occ.id,
        tier=occ.tier or 0,
        urgency=rem.priority or "normal",
        links=channels.build_links(db, occ.id),
        contact_phone=rem.contact_phone,
        contact_url=rem.contact_url,
        tally=attempts + 1,
        lang=lang,
    )


def profile_for(rem: Reminder, occ: Occurrence) -> escalation.Profile:
    """Escalation profile for one occurrence.

    A stage may override the reminder's intensity: the errand that unblocks
    everything deserves chasing, while a heads-up does not need to be closed at
    all hours. Falls back to the reminder when the stage says nothing.
    """
    stages = rem.stages or []
    idx = occ.stage_index or 0
    if 0 <= idx < len(stages):
        override = (stages[idx] or {}).get("intensity")
        if override in escalation.PROFILES:
            return escalation.get_profile(override)
    return escalation.get_profile(rem.intensity)


def allowed_channels(db: Session, rem: Reminder, tier: int) -> list[str]:
    """Intersect the tier's channels with what this reminder permits."""
    tier_channels = escalation.channels_for_tier(tier)
    override = rem.channels or []
    if override:
        # A reminder pinned to specific channels still escalates in frequency,
        # it just never widens beyond what you allowed.
        return [c for c in tier_channels if c in override] or list(override)
    default = settings_store.get(db, "default_channels", ["push"]) or ["push"]
    # Tier 0 respects the default set; higher tiers are allowed to widen.
    if tier == 0:
        return [c for c in tier_channels if c in default] or tier_channels[:1]
    return tier_channels


# --------------------------------------------------------------------------
# The tick
# --------------------------------------------------------------------------


def tick(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    lang = settings_store.get(db, "lang", "he")
    stats = {"promoted": 0, "woken": 0, "notified": 0, "missed": 0, "deliveries": 0}

    # 1. Anything whose time has arrived becomes an open loop.
    promoted = (
        db.query(Occurrence)
        .filter(Occurrence.status == "scheduled", Occurrence.due_at <= now)
        .all()
    )
    for occ in promoted:
        occ.status = "active"
        if occ.next_attempt_at is None:
            occ.next_attempt_at = occ.due_at
        stats["promoted"] += 1

    # 2. Expired snoozes come back.
    woken = (
        db.query(Occurrence)
        .filter(
            Occurrence.status == "snoozed",
            Occurrence.snooze_until.isnot(None),
            Occurrence.snooze_until <= now,
        )
        .all()
    )
    for occ in woken:
        occ.status = "active"
        occ.next_attempt_at = now
        stats["woken"] += 1

    db.flush()

    # 3. Send the next rung for everything that is open and due an attempt.
    due = (
        db.query(Occurrence)
        .filter(
            Occurrence.status == "active",
            or_(Occurrence.next_attempt_at.is_(None), Occurrence.next_attempt_at <= now),
        )
        .order_by(Occurrence.due_at)
        .limit(200)
        .all()
    )

    for occ in due:
        rem = occ.reminder
        if rem is None or not rem.active:
            occ.status = "cancelled"
            continue

        # Give up on the truly ancient rather than nag forever about something
        # that has clearly been overtaken by events.
        if occ.due_at < now - timedelta(days=GIVE_UP_DAYS):
            occ.status = "missed"
            stats["missed"] += 1
            log_event(db, "missed", f"{rem.title} — {occ.stage_label or ''}".strip(" —"),
                      {"occurrence_id": occ.id})
            continue

        critical = (rem.priority == "critical") or rem.ignore_quiet_hours
        if not critical and in_quiet_hours(db, now):
            occ.next_attempt_at = next_quiet_end(db, now)
            continue

        profile = profile_for(rem, occ)
        attempts = occ.attempts or 0
        _, tier = escalation.plan_attempt(profile, attempts)

        # Repeat snoozers do not get to ride the bottom rung forever.
        if (occ.snooze_count or 0) >= SNOOZE_PATIENCE:
            tier = max(tier, 2)

        occ.tier = tier
        msg = render(db, occ, rem, lang)
        priority = escalation.ntfy_priority(tier, critical=critical)

        sent_any = False
        for channel in allowed_channels(db, rem, tier):
            ok, _detail = channels.dispatch(db, channel, msg, ntfy_priority=priority)
            if ok:
                sent_any = True
                stats["deliveries"] += 1

        occ.attempts = attempts + 1
        occ.last_attempt_at = now
        stats["notified"] += 1

        # Schedule the following rung, measured from the due time so a late
        # tick cannot compress the whole ladder into one burst.
        # An exhausted profile (gentle) already yields an offset roughly a
        # century out, which parks it permanently -- do NOT null the field
        # here, because the tick query treats NULL as "due now" and would
        # re-fire it forever.
        next_offset, _ = escalation.plan_attempt(profile, occ.attempts)
        planned = occ.due_at + timedelta(minutes=next_offset)
        occ.next_attempt_at = max(planned, now + timedelta(minutes=1))

        if not sent_any and not escalation.is_terminal(profile, occ.attempts):
            # Nothing got through. Come back sooner, but keep climbing the
            # ladder anyway: higher tiers try more channels, and one of those
            # may be the one that actually works. Holding the ladder still
            # would leave a reminder with no working channel spinning at tier 0
            # forever, never escalating and never showing a nag tally.
            #
            # Excluded once the profile is exhausted (a gentle stage that has
            # said its piece): retrying a rung that is already parked would
            # turn "gentle" into a ten-minute loop, which is the opposite of
            # what it promises.
            occ.next_attempt_at = min(
                occ.next_attempt_at, now + timedelta(minutes=10)
            )

        _maybe_escalate_to_buddy(db, occ, rem, msg, lang)

    db.commit()
    return stats


def _maybe_escalate_to_buddy(
    db: Session, occ: Occurrence, rem: Reminder, msg: channels.Message, lang: str
) -> None:
    """Tell somebody else you are still dodging it.

    Social pressure is the last rung, and it only applies to reminders you
    explicitly opted in.
    """
    if not rem.escalate_to_buddy or not settings_store.get(db, "buddy_enabled", False):
        return
    threshold = int(settings_store.get(db, "buddy_after_attempts", 8) or 8)
    if (occ.attempts or 0) != threshold:
        return  # fire exactly once, at the threshold

    name = settings_store.get(db, "buddy_name", "") or "?"
    age = humanise_delta(int((utcnow() - occ.due_at).total_seconds() // 60), lang)
    buddy_msg = channels.Message(
        title=t("buddy_subject", lang, name=name),
        body=t("buddy_body", lang, title=rem.title, age=age, n=occ.attempts),
        occurrence_id=occ.id,
        tier=4,
        links={},
        lang=lang,
    )

    chat = settings_store.get(db, "buddy_telegram_chat_id", "")
    if chat:
        ok, detail = channels.send_telegram(db, buddy_msg, chat_id=chat)
        db.add_all([])
        log_event(db, "buddy", f"Told {name} about {rem.title}", {"ok": ok, "detail": detail})

    email = settings_store.get(db, "buddy_email", "")
    if email:
        ok, detail = channels.send_email(db, buddy_msg, to=email)
        log_event(db, "buddy", f"Emailed {name} about {rem.title}", {"ok": ok, "detail": detail})


# --------------------------------------------------------------------------
# Human actions -- the only things that close a loop
# --------------------------------------------------------------------------


def mark_done(db: Session, occ: Occurrence, via: str = "app", answer: str | None = None) -> None:
    if occ.status in ("done", "skipped"):
        return
    occ.status = "done"
    occ.done_at = utcnow()
    occ.done_via = via
    occ.next_attempt_at = None
    if answer:
        occ.confirm_answer = answer

    rem = occ.reminder
    if rem is not None:
        log_event(
            db,
            "done",
            f"{rem.title} — {occ.stage_label or ''}".strip(" —"),
            {"occurrence_id": occ.id, "via": via, "attempts": occ.attempts},
        )
        # Completing the main stage of a completion-anchored reminder starts
        # the next cycle counting from today.
        if rem.anchor_to_completion and occ.stage_kind == "main":
            spawn_next_cycle(db, rem, occ.done_at)
    db.commit()


def mark_skipped(db: Session, occ: Occurrence, via: str = "app") -> None:
    if occ.status in ("done", "skipped"):
        return
    occ.status = "skipped"
    occ.done_at = utcnow()
    occ.done_via = via
    occ.next_attempt_at = None
    rem = occ.reminder
    if rem is not None:
        log_event(db, "skipped", rem.title, {"occurrence_id": occ.id, "via": via})
        if rem.anchor_to_completion and occ.stage_kind == "main":
            spawn_next_cycle(db, rem, utcnow())
    db.commit()


def snooze(
    db: Session,
    occ: Occurrence,
    *,
    preset: str | None = None,
    minutes: int | None = None,
    via: str = "app",
) -> datetime:
    until = resolve_snooze(db, preset, minutes)
    occ.status = "snoozed"
    occ.snooze_until = until
    occ.snooze_count = (occ.snooze_count or 0) + 1
    occ.next_attempt_at = until
    log_event(
        db,
        "snoozed",
        f"{occ.reminder.title if occ.reminder else ''}",
        {"occurrence_id": occ.id, "until": until.isoformat(), "count": occ.snooze_count, "via": via},
    )
    db.commit()
    return until


def reopen(db: Session, occ: Occurrence) -> None:
    """Undo a close. Everyone taps the wrong button eventually."""
    occ.status = "active"
    occ.done_at = None
    occ.done_via = None
    occ.next_attempt_at = utcnow()
    db.commit()
