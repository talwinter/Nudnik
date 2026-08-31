"""HTTP API.

Two audiences share one surface: the admin console (same-origin, cookie or
open) and external integrations (``X-API-Key``). Anything that mutates state
goes through the engine so the audit trail stays complete.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import (
    analytics,
    channels,
    digest,
    engine,
    escalation,
    nlp,
    presets,
    scheduler,
    security,
    settings_store,
)
from .db import (
    Event,
    NotificationLog,
    Occurrence,
    PushSubscription,
    Reminder,
    SessionLocal,
    log_event,
    utcnow,
)
from .i18n import t
from .recurrence import materialise, normalise_stages, resync
from .schemas import (
    DoneIn,
    PushSubIn,
    QuickAddIn,
    ReminderIn,
    ReminderPatch,
    SettingsPatch,
    SnoozeIn,
    TestChannelIn,
)

router = APIRouter(prefix="/api")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------
# Reminders
# --------------------------------------------------------------------------


def _reminder_dict(rem: Reminder, db: Session) -> dict:
    open_count = sum(
        1 for o in rem.occurrences if o.status in ("active", "snoozed", "scheduled")
    )
    overdue = sum(
        1
        for o in rem.occurrences
        if o.status in ("active", "snoozed") and o.due_at < utcnow()
    )
    next_occ = min(
        (o for o in rem.occurrences if o.status in ("scheduled", "active", "snoozed")),
        key=lambda o: o.due_at,
        default=None,
    )
    return {
        "id": rem.id,
        "title": rem.title,
        "notes": rem.notes,
        "category": rem.category,
        "emoji": rem.emoji,
        "priority": rem.priority,
        "anchor_at": rem.anchor_at.isoformat(),
        "all_day": rem.all_day,
        "tz": rem.tz,
        "repeat_kind": rem.repeat_kind,
        "repeat_interval": rem.repeat_interval,
        "repeat_weekdays": rem.repeat_weekdays,
        "anchor_to_completion": rem.anchor_to_completion,
        "repeat_until": rem.repeat_until.isoformat() if rem.repeat_until else None,
        "repeat_count": rem.repeat_count,
        "cycles_done": rem.cycles_done,
        "stages": rem.stages or [],
        "intensity": rem.intensity,
        "channels": rem.channels or [],
        "ignore_quiet_hours": rem.ignore_quiet_hours,
        "contact_phone": rem.contact_phone,
        "contact_url": rem.contact_url,
        "require_confirmation": rem.require_confirmation,
        "escalate_to_buddy": rem.escalate_to_buddy,
        "active": rem.active,
        "created_at": rem.created_at.isoformat() if rem.created_at else None,
        "open_count": open_count,
        "overdue_count": overdue,
        "next_due": next_occ.due_at.isoformat() if next_occ else None,
        "next_label": next_occ.stage_label if next_occ else None,
    }


def _occ_dict(occ: Occurrence) -> dict:
    rem = occ.reminder
    return {
        "id": occ.id,
        "reminder_id": occ.reminder_id,
        "title": rem.title if rem else "",
        "emoji": rem.emoji if rem else "",
        "category": rem.category if rem else "general",
        "priority": rem.priority if rem else "normal",
        "intensity": rem.intensity if rem else "relentless",
        "contact_phone": rem.contact_phone if rem else None,
        "contact_url": rem.contact_url if rem else None,
        "require_confirmation": rem.require_confirmation if rem else False,
        "notes": rem.notes if rem else None,
        "cycle": occ.cycle,
        "stage_index": occ.stage_index,
        "stage_label": occ.stage_label,
        "stage_kind": occ.stage_kind,
        "due_at": occ.due_at.isoformat(),
        "status": occ.status,
        "snooze_until": occ.snooze_until.isoformat() if occ.snooze_until else None,
        "snooze_count": occ.snooze_count or 0,
        "attempts": occ.attempts or 0,
        "tier": occ.tier or 0,
        "last_attempt_at": occ.last_attempt_at.isoformat() if occ.last_attempt_at else None,
        "next_attempt_at": occ.next_attempt_at.isoformat() if occ.next_attempt_at else None,
        "done_at": occ.done_at.isoformat() if occ.done_at else None,
        "done_via": occ.done_via,
        "is_overdue": occ.status in ("active", "snoozed") and occ.due_at < utcnow(),
    }


def _apply_payload(rem: Reminder, data: dict) -> None:
    for field in (
        "title", "notes", "category", "emoji", "priority", "all_day", "repeat_kind",
        "repeat_interval", "repeat_weekdays", "anchor_to_completion", "repeat_count",
        "intensity", "ignore_quiet_hours", "contact_phone", "contact_url",
        "require_confirmation", "escalate_to_buddy", "active", "tz",
    ):
        if field in data and data[field] is not None:
            setattr(rem, field, data[field])
    if data.get("anchor_at"):
        rem.anchor_at = _naive(data["anchor_at"])
    if "repeat_until" in data:
        rem.repeat_until = _naive(data["repeat_until"]) if data["repeat_until"] else None
    if data.get("stages") is not None:
        rem.stages = normalise_stages(
            [s if isinstance(s, dict) else s.model_dump() for s in data["stages"]]
        )
    if data.get("channels") is not None:
        rem.channels = list(data["channels"])


def _naive(value) -> datetime:
    """Everything is stored as naive UTC."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is not None:
        value = value.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return value


@router.get("/reminders")
def list_reminders(
    db: Session = Depends(get_db),
    include_inactive: bool = Query(False),
    category: str | None = None,
    search: str | None = None,
):
    q = db.query(Reminder)
    if not include_inactive:
        q = q.filter(Reminder.active.is_(True))
    if category and category != "all":
        q = q.filter(Reminder.category == category)
    if search:
        like = f"%{search}%"
        q = q.filter(Reminder.title.ilike(like) | Reminder.notes.ilike(like))
    rows = q.order_by(Reminder.anchor_at).all()
    return [_reminder_dict(r, db) for r in rows]


@router.post("/reminders")
def create_reminder(payload: ReminderIn, db: Session = Depends(get_db)):
    rem = Reminder(anchor_at=_naive(payload.anchor_at))
    data = payload.model_dump()
    _apply_payload(rem, data)
    if not rem.tz:
        rem.tz = settings_store.get(db, "timezone", "Asia/Jerusalem")
    if not rem.stages:
        rem.stages = normalise_stages([])
    db.add(rem)
    db.flush()
    created = materialise(db, rem)
    log_event(db, "created", rem.title, {"reminder_id": rem.id, "occurrences": created})
    db.commit()
    db.refresh(rem)
    return _reminder_dict(rem, db)


@router.get("/reminders/{reminder_id}")
def get_reminder(reminder_id: int, db: Session = Depends(get_db)):
    rem = db.get(Reminder, reminder_id)
    if not rem:
        raise HTTPException(404, "Reminder not found")
    data = _reminder_dict(rem, db)
    data["occurrences"] = [_occ_dict(o) for o in sorted(rem.occurrences, key=lambda o: o.due_at)]
    return data


@router.patch("/reminders/{reminder_id}")
def update_reminder(reminder_id: int, payload: ReminderPatch, db: Session = Depends(get_db)):
    rem = db.get(Reminder, reminder_id)
    if not rem:
        raise HTTPException(404, "Reminder not found")
    _apply_payload(rem, payload.model_dump(exclude_unset=True))
    db.flush()
    resync(db, rem)
    log_event(db, "updated", rem.title, {"reminder_id": rem.id})
    db.commit()
    db.refresh(rem)
    return _reminder_dict(rem, db)


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    rem = db.get(Reminder, reminder_id)
    if not rem:
        raise HTTPException(404, "Reminder not found")
    title = rem.title
    db.delete(rem)
    log_event(db, "deleted", title, {"reminder_id": reminder_id})
    db.commit()
    return {"ok": True}


@router.post("/reminders/{reminder_id}/duplicate")
def duplicate_reminder(reminder_id: int, db: Session = Depends(get_db)):
    src = db.get(Reminder, reminder_id)
    if not src:
        raise HTTPException(404, "Reminder not found")
    clone = Reminder(
        title=f"{src.title} (2)",
        notes=src.notes,
        category=src.category,
        emoji=src.emoji,
        priority=src.priority,
        anchor_at=src.anchor_at,
        all_day=src.all_day,
        tz=src.tz,
        repeat_kind=src.repeat_kind,
        repeat_interval=src.repeat_interval,
        repeat_weekdays=src.repeat_weekdays,
        anchor_to_completion=src.anchor_to_completion,
        stages=src.stages,
        intensity=src.intensity,
        channels=src.channels,
        contact_phone=src.contact_phone,
        contact_url=src.contact_url,
        require_confirmation=src.require_confirmation,
        escalate_to_buddy=src.escalate_to_buddy,
    )
    db.add(clone)
    db.flush()
    materialise(db, clone)
    db.commit()
    db.refresh(clone)
    return _reminder_dict(clone, db)


# --------------------------------------------------------------------------
# Occurrences -- the open loops
# --------------------------------------------------------------------------


@router.get("/occurrences")
def list_occurrences(
    db: Session = Depends(get_db),
    status: str = Query("open"),
    days: int = Query(30),
    limit: int = Query(300),
):
    q = db.query(Occurrence).join(Reminder, Occurrence.reminder_id == Reminder.id)

    if status == "open":
        q = q.filter(Occurrence.status.in_(("active", "snoozed")))
    elif status == "overdue":
        q = q.filter(
            Occurrence.status.in_(("active", "snoozed")), Occurrence.due_at < utcnow()
        )
    elif status == "upcoming":
        q = q.filter(
            Occurrence.status == "scheduled",
            Occurrence.due_at <= utcnow() + timedelta(days=days),
        )
    elif status == "closed":
        q = q.filter(Occurrence.status.in_(("done", "skipped", "missed")))
    elif status != "all":
        q = q.filter(Occurrence.status == status)

    rows = q.order_by(Occurrence.due_at).limit(limit).all()
    return [_occ_dict(o) for o in rows]


@router.get("/occurrences/{occ_id}")
def get_occurrence(occ_id: int, db: Session = Depends(get_db)):
    occ = db.get(Occurrence, occ_id)
    if not occ:
        raise HTTPException(404, "Occurrence not found")
    data = _occ_dict(occ)
    data["logs"] = [
        {
            "channel": log.channel,
            "tier": log.tier,
            "status": log.status,
            "detail": log.detail,
            "created_at": log.created_at.isoformat(),
        }
        for log in sorted(occ.logs, key=lambda log: log.created_at, reverse=True)
    ]
    return data


@router.post("/occurrences/{occ_id}/done")
def done(occ_id: int, payload: DoneIn | None = None, db: Session = Depends(get_db)):
    occ = db.get(Occurrence, occ_id)
    if not occ:
        raise HTTPException(404, "Occurrence not found")
    engine.mark_done(db, occ, via="app", answer=payload.answer if payload else None)
    return _occ_dict(occ)


@router.post("/occurrences/{occ_id}/skip")
def skip(occ_id: int, db: Session = Depends(get_db)):
    occ = db.get(Occurrence, occ_id)
    if not occ:
        raise HTTPException(404, "Occurrence not found")
    engine.mark_skipped(db, occ, via="app")
    return _occ_dict(occ)


@router.post("/occurrences/{occ_id}/snooze")
def snooze(occ_id: int, payload: SnoozeIn, db: Session = Depends(get_db)):
    occ = db.get(Occurrence, occ_id)
    if not occ:
        raise HTTPException(404, "Occurrence not found")
    until = engine.snooze(db, occ, preset=payload.preset, minutes=payload.minutes, via="app")
    return {**_occ_dict(occ), "snoozed_until": until.isoformat()}


@router.post("/occurrences/{occ_id}/reopen")
def reopen(occ_id: int, db: Session = Depends(get_db)):
    occ = db.get(Occurrence, occ_id)
    if not occ:
        raise HTTPException(404, "Occurrence not found")
    engine.reopen(db, occ)
    return _occ_dict(occ)


@router.post("/occurrences/{occ_id}/call-assist")
def call_assist(occ_id: int, db: Session = Depends(get_db)):
    """Ask a voice provider to place the call and connect you when a human answers.

    The reminder that gets dodged is almost never the task -- it is the phone
    call in front of it. This hands the dialling, the hold queue and the IVR to
    whichever provider you configure, and rings you only once a person is on
    the line.

    Nudnik stays provider-agnostic on purpose: it POSTs a plain JSON request
    and treats any 2xx as accepted. Point it at Bland/Vapi/Retell, a Twilio
    function, or your own Asterisk dialplan.
    """
    import httpx as _httpx

    occ = db.get(Occurrence, occ_id)
    if not occ:
        raise HTTPException(404, "Occurrence not found")
    if not settings_store.get(db, "callassist_enabled", False):
        raise HTTPException(400, "Call assist is not enabled")

    url = settings_store.get(db, "callassist_url", "")
    my_number = settings_store.get(db, "callassist_my_number", "")
    rem = occ.reminder
    target = rem.contact_phone if rem else None

    if not url or not my_number:
        raise HTTPException(400, "Call assist needs a provider URL and your own number")
    if not target:
        raise HTTPException(400, "This reminder has no phone number to call")

    payload = {
        "occurrence_id": occ.id,
        "call_to": target,
        "connect_to": my_number,
        "task": occ.stage_label or (rem.title if rem else ""),
        "context": (rem.notes if rem else "") or "",
        "language": settings_store.get(db, "lang", "he"),
        # So the provider can close the loop itself once the call succeeds.
        "done_url": security.action_url(db, occ.id, "done"),
    }
    headers = {}
    token = settings_store.get(db, "callassist_token", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with _httpx.Client(timeout=20) as client:
            resp = client.post(url, json=payload, headers=headers)
        ok = resp.status_code < 300
        detail = f"{resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, str(exc)

    db.add(
        NotificationLog(
            occurrence_id=occ.id,
            channel="call-assist",
            tier=occ.tier or 0,
            status="ok" if ok else "failed",
            detail=detail[:1000],
        )
    )
    log_event(db, "call_assist", f"Requested a call to {target}", {"ok": ok})
    db.commit()
    if not ok:
        raise HTTPException(502, f"Call provider rejected the request ({detail})")
    return {"ok": True, "detail": detail, "calling": target, "connecting": my_number}


@router.post("/occurrences/{occ_id}/nudge")
def nudge_now(occ_id: int, db: Session = Depends(get_db)):
    """Force the next rung immediately. Used by the admin console to test."""
    occ = db.get(Occurrence, occ_id)
    if not occ:
        raise HTTPException(404, "Occurrence not found")
    if occ.status == "scheduled":
        occ.status = "active"
    occ.next_attempt_at = utcnow()
    db.commit()
    return engine.tick(db)


# --------------------------------------------------------------------------
# Quick add
# --------------------------------------------------------------------------


@router.post("/quick-add")
def quick_add(payload: QuickAddIn, db: Session = Depends(get_db)):
    lang = settings_store.get(db, "lang", "he")
    tz = ZoneInfo(settings_store.get(db, "timezone", "Asia/Jerusalem"))
    now_local = datetime.now(tz).replace(tzinfo=None)

    parsed = nlp.parse(payload.text, now_local)
    when_local = parsed["when"] or (now_local + timedelta(hours=1))
    anchor_utc = (
        when_local.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    )

    preview = {
        "title": parsed["title"],
        "anchor_at": anchor_utc.isoformat(),
        "anchor_local": when_local.isoformat(),
        "repeat_kind": parsed["repeat_kind"],
        "repeat_interval": parsed["repeat_interval"],
        "confidence": parsed["confidence"],
    }
    if payload.dry_run:
        return preview

    stages = normalise_stages([])
    preset_data = presets.get_preset(payload.preset) if payload.preset else None
    category, emoji, intensity = "general", "", settings_store.get(
        db, "default_intensity", "relentless"
    )
    anchor_to_completion = False
    if preset_data:
        category = preset_data["category"]
        emoji = preset_data["emoji"]
        intensity = preset_data.get("intensity", intensity)
        anchor_to_completion = preset_data.get("anchor_to_completion", False)
        stages = normalise_stages(
            [
                {
                    "offset_minutes": s["offset_minutes"],
                    "kind": s["kind"],
                    "label": s["label"].get(lang, s["label"].get("en", "")),
                }
                for s in preset_data["stages"]
            ]
        )

    rem = Reminder(
        title=parsed["title"],
        category=category,
        emoji=emoji,
        anchor_at=anchor_utc,
        tz=str(tz),
        repeat_kind=parsed["repeat_kind"],
        repeat_interval=parsed["repeat_interval"],
        anchor_to_completion=anchor_to_completion,
        stages=stages,
        intensity=intensity,
    )
    db.add(rem)
    db.flush()
    materialise(db, rem)
    log_event(db, "created", rem.title, {"reminder_id": rem.id, "via": "quick-add"})
    db.commit()
    db.refresh(rem)
    return {**_reminder_dict(rem, db), "parsed": preview}


# --------------------------------------------------------------------------
# Dashboard, analytics, presets
# --------------------------------------------------------------------------


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    now = utcnow()
    open_q = db.query(Occurrence).filter(Occurrence.status.in_(("active", "snoozed")))
    overdue = [o for o in open_q.order_by(Occurrence.due_at).all() if o.due_at < now]
    today_end = now + timedelta(hours=24)
    today = (
        db.query(Occurrence)
        .filter(
            Occurrence.status.in_(("active", "snoozed", "scheduled")),
            Occurrence.due_at >= now,
            Occurrence.due_at <= today_end,
        )
        .order_by(Occurrence.due_at)
        .all()
    )
    upcoming = (
        db.query(Occurrence)
        .filter(
            Occurrence.status == "scheduled",
            Occurrence.due_at > today_end,
            Occurrence.due_at <= now + timedelta(days=30),
        )
        .order_by(Occurrence.due_at)
        .limit(40)
        .all()
    )
    return {
        "overdue": [_occ_dict(o) for o in overdue],
        "today": [_occ_dict(o) for o in today],
        "upcoming": [_occ_dict(o) for o in upcoming],
        "stats": analytics.overview(db),
        "channels": channels.configured_channels(db),
        "worst_offender": max(
            (_occ_dict(o) for o in overdue), key=lambda o: o["attempts"], default=None
        ),
    }


@router.get("/analytics")
def get_analytics(days: int = 90, db: Session = Depends(get_db)):
    return {
        "overview": analytics.overview(db, days),
        "channels": analytics.channel_effectiveness(db, days),
        "problems": analytics.problem_reminders(db),
        "series": analytics.activity_series(db, min(days, 60)),
    }


@router.get("/presets")
def get_presets(db: Session = Depends(get_db)):
    lang = settings_store.get(db, "lang", "he")
    return {"presets": presets.localised_presets(lang), "categories": presets.CATEGORIES}


@router.get("/events")
def list_events(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(Event).order_by(Event.created_at.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "kind": e.kind,
            "summary": e.summary,
            "meta": e.meta,
            "created_at": e.created_at.isoformat(),
        }
        for e in rows
    ]


@router.get("/logs")
def list_logs(limit: int = 200, channel: str | None = None, db: Session = Depends(get_db)):
    q = db.query(NotificationLog)
    if channel:
        q = q.filter(NotificationLog.channel == channel)
    rows = q.order_by(NotificationLog.created_at.desc()).limit(limit).all()
    out = []
    for log in rows:
        occ = log.occurrence
        out.append(
            {
                "id": log.id,
                "occurrence_id": log.occurrence_id,
                "title": (occ.reminder.title if occ and occ.reminder else None),
                "stage": occ.stage_label if occ else None,
                "channel": log.channel,
                "tier": log.tier,
                "status": log.status,
                "detail": log.detail,
                "created_at": log.created_at.isoformat(),
            }
        )
    return out


# --------------------------------------------------------------------------
# Settings and channels
# --------------------------------------------------------------------------

SECRET_KEYS = {
    "vapid_private", "telegram_token", "smtp_pass", "twilio_auth",
    "api_key", "ics_token", "secret_key", "ntfy_token", "gotify_token",
    "matrix_token",
}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    values = settings_store.all_settings(db)
    masked = {}
    for key, value in values.items():
        if key in SECRET_KEYS and value:
            masked[key] = "••••••••"
            masked[f"{key}__set"] = True
        else:
            masked[key] = value
    masked["channels_ready"] = channels.configured_channels(db)
    masked["scheduler"] = scheduler.status()
    masked["push_device_count"] = db.query(PushSubscription).count()
    return masked


@router.get("/settings/reveal")
def reveal_secret(key: str = Query(...), db: Session = Depends(get_db)):
    """Return one secret in cleartext.

    The settings payload masks secrets so they cannot leak into a screenshot or
    a cached response, but you still have to be able to copy your own API key
    and calendar token. Only the keys that are meant to be copied are exposed;
    passwords and private keys are never returned.
    """
    COPYABLE = {"api_key", "ics_token", "ntfy_topic"}
    if key not in COPYABLE:
        raise HTTPException(403, "That value cannot be revealed")
    return {"key": key, "value": settings_store.get(db, key, "")}


@router.patch("/settings")
def patch_settings(payload: SettingsPatch, db: Session = Depends(get_db)):
    for key, value in payload.values.items():
        if key not in settings_store.DEFAULTS:
            continue
        # A masked secret coming back unchanged must not overwrite the real one.
        if key in SECRET_KEYS and value == "••••••••":
            continue
        settings_store.set_value(db, key, value)
    settings_store.invalidate()
    log_event(db, "settings", f"Updated {len(payload.values)} setting(s)")
    db.commit()
    return get_settings(db)


@router.post("/channels/test")
def test_channel(payload: TestChannelIn, db: Session = Depends(get_db)):
    lang = settings_store.get(db, "lang", "he")
    base = settings_store.get(db, "public_url", "").rstrip("/")
    msg = channels.Message(
        title=t("test_title", lang) + f" · {payload.channel}",
        body=t("test_body", lang),
        tier=1,
        links={"open": base or "/"},
        lang=lang,
    )
    ok, detail = channels.dispatch(db, payload.channel, msg, log=False, ntfy_priority=4)
    db.add(
        NotificationLog(
            occurrence_id=None,
            channel=payload.channel,
            tier=0,
            status="ok" if ok else "failed",
            detail=f"[test] {detail}"[:1000],
        )
    )
    db.commit()
    return {"ok": ok, "detail": detail}


@router.get("/channels")
def channel_status(db: Session = Depends(get_db)):
    ready = channels.configured_channels(db)
    recent = (
        db.query(
            NotificationLog.channel,
            NotificationLog.status,
            func.count(NotificationLog.id),
        )
        .filter(NotificationLog.created_at >= utcnow() - timedelta(days=7))
        .group_by(NotificationLog.channel, NotificationLog.status)
        .all()
    )
    counts: dict[str, dict[str, int]] = {}
    for channel, status, count in recent:
        counts.setdefault(channel, {})[status] = count

    return [
        {
            "channel": name,
            "ready": ready.get(name, False),
            "tiers": [tier for tier, chans in escalation.TIER_CHANNELS.items() if name in chans],
            "last_7d": counts.get(name, {}),
        }
        for name in channels.ALL_CHANNELS
    ]


# --------------------------------------------------------------------------
# Push subscription management
# --------------------------------------------------------------------------


@router.get("/push/key")
def push_key(db: Session = Depends(get_db)):
    return {
        "publicKey": settings_store.get(db, "vapid_public", ""),
        "enabled": bool(settings_store.get(db, "push_enabled", True)),
    }


@router.post("/push/subscribe")
def push_subscribe(payload: PushSubIn, request: Request, db: Session = Depends(get_db)):
    keys = payload.keys or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not p256dh or not auth:
        raise HTTPException(400, "Subscription is missing encryption keys")

    existing = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == payload.endpoint)
        .first()
    )
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
        existing.failures = 0
        existing.last_ok_at = utcnow()
    else:
        db.add(
            PushSubscription(
                endpoint=payload.endpoint,
                p256dh=p256dh,
                auth=auth,
                user_agent=request.headers.get("user-agent", "")[:400],
                label=payload.label,
            )
        )
        log_event(db, "push", "New device subscribed", {"label": payload.label})
    db.commit()
    return {"ok": True, "devices": db.query(PushSubscription).count()}


@router.post("/push/unsubscribe")
def push_unsubscribe(payload: dict, db: Session = Depends(get_db)):
    endpoint = payload.get("endpoint")
    if endpoint:
        db.query(PushSubscription).filter(
            PushSubscription.endpoint == endpoint
        ).delete(synchronize_session=False)
        db.commit()
    return {"ok": True}


@router.get("/push/devices")
def push_devices(db: Session = Depends(get_db)):
    return [
        {
            "id": s.id,
            "label": s.label,
            "user_agent": s.user_agent,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "last_ok_at": s.last_ok_at.isoformat() if s.last_ok_at else None,
            "failures": s.failures,
            "endpoint_host": (s.endpoint or "").split("/")[2] if "/" in (s.endpoint or "") else "",
            # Enough for a browser to recognise its own subscription in this
            # list, without returning full endpoints to the page.
            "endpoint_tail": (s.endpoint or "")[-16:],
        }
        for s in db.query(PushSubscription).all()
    ]


@router.delete("/push/devices/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    db.query(PushSubscription).filter(PushSubscription.id == device_id).delete()
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Engine control
# --------------------------------------------------------------------------


@router.post("/tick")
def manual_tick(
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    key: str | None = Query(default=None),
):
    """Drive the engine from outside.

    Exposed so a free host that sleeps can be woken by an external cron and
    still deliver on time. Requires the API key in either header or query, the
    latter because most cron pingers cannot set headers.
    """
    security.require_api_key(db, x_api_key or key)
    return engine.tick(db)


@router.post("/brief/send")
def send_brief_now(db: Session = Depends(get_db)):
    return digest.send_daily_brief(db)


@router.get("/brief/preview")
def brief_preview(db: Session = Depends(get_db)):
    return digest.preview(db)


@router.get("/health")
def health(db: Session = Depends(get_db)):
    open_count = (
        db.query(Occurrence).filter(Occurrence.status.in_(("active", "snoozed"))).count()
    )
    return {
        "ok": True,
        "time": utcnow().isoformat() + "Z",
        "open_loops": open_count,
        "scheduler": scheduler.status(),
        "features": {
            "call_assist": bool(
                settings_store.get(db, "callassist_enabled", False)
                and settings_store.get(db, "callassist_url", "")
                and settings_store.get(db, "callassist_my_number", "")
            ),
        },
    }


# --------------------------------------------------------------------------
# Import / export
# --------------------------------------------------------------------------


@router.get("/export")
def export_all(db: Session = Depends(get_db)):
    rems = db.query(Reminder).all()
    return {
        "version": 2,
        "exported_at": utcnow().isoformat(),
        "reminders": [
            {
                k: v
                for k, v in _reminder_dict(r, db).items()
                if k not in ("open_count", "overdue_count", "next_due", "next_label")
            }
            for r in rems
        ],
    }


@router.post("/import")
def import_all(payload: dict, db: Session = Depends(get_db)):
    items = payload.get("reminders", [])
    created = 0
    for item in items:
        rem = Reminder(anchor_at=_naive(item["anchor_at"]))
        _apply_payload(rem, item)
        db.add(rem)
        db.flush()
        materialise(db, rem)
        created += 1
    log_event(db, "import", f"Imported {created} reminders")
    db.commit()
    return {"ok": True, "created": created}


# --------------------------------------------------------------------------
# Calendar feed
# --------------------------------------------------------------------------


def _ics_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


@router.get("/calendar.ics", response_class=PlainTextResponse)
def calendar_feed(token: str = Query(...), db: Session = Depends(get_db)):
    """Subscribe from Google or Apple Calendar.

    Read-only on purpose: the calendar shows what is coming, the app remains
    the only place a loop can actually be closed.
    """
    expected = settings_store.get(db, "ics_token", "")
    if not expected or token != expected:
        raise HTTPException(403, "Invalid calendar token")

    rows = (
        db.query(Occurrence)
        .join(Reminder, Occurrence.reminder_id == Reminder.id)
        .filter(
            Reminder.active.is_(True),
            Occurrence.status.in_(("scheduled", "active", "snoozed")),
            Occurrence.due_at >= utcnow() - timedelta(days=30),
        )
        .order_by(Occurrence.due_at)
        .limit(600)
        .all()
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Nudnik//Reminders//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Nudnik",
        "X-WR-TIMEZONE:" + settings_store.get(db, "timezone", "Asia/Jerusalem"),
    ]
    base = settings_store.get(db, "public_url", "").rstrip("/")
    for occ in rows:
        rem = occ.reminder
        stamp = occ.due_at.strftime("%Y%m%dT%H%M%SZ")
        end = (occ.due_at + timedelta(minutes=30)).strftime("%Y%m%dT%H%M%SZ")
        summary = occ.stage_label or rem.title
        if rem.emoji:
            summary = f"{rem.emoji} {summary}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:nudnik-{occ.id}@nudnik",
            f"DTSTAMP:{utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{stamp}",
            f"DTEND:{end}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(rem.title + (chr(10) + rem.notes if rem.notes else ''))}",
            f"URL:{base}/#/occurrence/{occ.id}",
            "BEGIN:VALARM",
            "TRIGGER:-PT0M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_escape(summary)}",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return PlainTextResponse(
        "\r\n".join(lines),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="nudnik.ics"'},
    )
