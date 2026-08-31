"""Key/value settings persisted in the database.

Env vars seed the initial values; after that the admin UI owns them. Values are
stored as JSON so booleans, numbers and nested channel config round-trip.
"""
import json
import os
import secrets
from typing import Any

from sqlalchemy.orm import Session

from . import config
from .db import Setting

# key -> (default, env var name or None)
DEFAULTS: dict[str, tuple[Any, str | None]] = {
    "public_url": (config.PUBLIC_URL, "PUBLIC_URL"),
    "lang": (config.DEFAULT_LANG, "DEFAULT_LANG"),
    "timezone": (config.DEFAULT_TZ, "DEFAULT_TZ"),
    "quiet_hours_enabled": (True, None),
    "quiet_start": ("23:00", None),
    "quiet_end": ("07:30", None),
    "brief_enabled": (True, None),
    "brief_time": ("08:30", None),
    "weekly_brief_enabled": (True, None),
    "weekly_brief_weekday": (6, None),  # 6 = Sunday, the Israeli week start
    "default_intensity": ("relentless", None),
    "default_channels": (["push"], None),
    # --- channels ---
    "push_enabled": (True, None),
    "vapid_public": ("", "VAPID_PUBLIC_KEY"),
    "vapid_private": ("", "VAPID_PRIVATE_KEY"),
    "vapid_subject": ("mailto:admin@localhost", "VAPID_SUBJECT"),
    "ntfy_enabled": (False, None),
    "ntfy_url": (os.getenv("NTFY_URL", "http://ntfy:80"), "NTFY_URL"),
    "ntfy_topic": ("", "NTFY_TOPIC"),
    "ntfy_token": ("", "NTFY_TOKEN"),
    "telegram_enabled": (False, None),
    "telegram_token": ("", "TELEGRAM_BOT_TOKEN"),
    "telegram_chat_id": ("", "TELEGRAM_CHAT_ID"),
    "email_enabled": (False, None),
    "smtp_host": ("", "SMTP_HOST"),
    "smtp_port": (587, "SMTP_PORT"),
    "smtp_user": ("", "SMTP_USER"),
    "smtp_pass": ("", "SMTP_PASS"),
    "smtp_tls": (True, None),
    "email_to": ("", "NOTIFY_EMAIL"),
    "gotify_enabled": (False, None),
    "gotify_url": ("", "GOTIFY_URL"),
    "gotify_token": ("", "GOTIFY_TOKEN"),
    "matrix_enabled": (False, None),
    "matrix_homeserver": ("", "MATRIX_HOMESERVER"),
    "matrix_token": ("", "MATRIX_TOKEN"),
    "matrix_room": ("", "MATRIX_ROOM"),
    "webhook_enabled": (False, None),
    "webhook_url": ("", "WEBHOOK_URL"),
    "webhook_method": ("POST", None),
    "webhook_headers": ({}, None),
    # Optional JSON body template. Lets the webhook channel speak any
    # third-party API shape without a dedicated integration.
    "webhook_template": ("", None),
    "sms_enabled": (False, None),
    "twilio_sid": ("", "TWILIO_SID"),
    "twilio_auth": ("", "TWILIO_AUTH"),
    "twilio_from": ("", "TWILIO_FROM"),
    "twilio_to": ("", "TWILIO_TO"),
    "whatsapp_enabled": (False, None),
    "whatsapp_from": ("", "TWILIO_WHATSAPP_FROM"),
    "whatsapp_to": ("", "TWILIO_WHATSAPP_TO"),
    # --- call assist ---
    # Provider-agnostic: Nudnik POSTs the call request and lets whatever you
    # point it at (Bland, Vapi, Retell, a Twilio function, your own Asterisk)
    # do the dialling and the warm transfer.
    "callassist_enabled": (False, None),
    "callassist_url": ("", "CALLASSIST_URL"),
    "callassist_token": ("", "CALLASSIST_TOKEN"),
    "callassist_my_number": ("", "CALLASSIST_MY_NUMBER"),
    # --- accountability ---
    "buddy_enabled": (False, None),
    "buddy_after_attempts": (8, None),
    "buddy_telegram_chat_id": ("", None),
    "buddy_email": ("", None),
    "buddy_name": ("", None),
    # --- misc ---
    "api_key": ("", "API_KEY"),
    "ics_token": ("", None),
    "secret_key": ("", "SECRET_KEY"),
}

_CACHE: dict[str, Any] = {}


def _coerce(raw: str, default: Any) -> Any:
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes", "on")
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(raw)
        except ValueError:
            return default
    if isinstance(default, (list, dict)):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default
    return raw


def bootstrap(db: Session) -> None:
    """Seed missing settings from env vars, generating secrets where needed."""
    existing = {s.key for s in db.query(Setting).all()}
    for key, (default, env_name) in DEFAULTS.items():
        if key in existing:
            continue
        value = default
        if env_name:
            raw = os.getenv(env_name)
            if raw:
                value = _coerce(raw, default)
        db.add(Setting(key=key, value=json.dumps(value)))
    db.commit()

    # Secrets are generated once and then reused, so action links stay valid
    # across restarts.
    for key, length in (("api_key", 32), ("ics_token", 24), ("secret_key", 48)):
        if not get(db, key):
            set_value(db, key, secrets.token_urlsafe(length))

    if not get(db, "ntfy_topic"):
        set_value(db, "ntfy_topic", f"nudnik-{secrets.token_hex(8)}")

    _CACHE.clear()


def get(db: Session, key: str, default: Any = None) -> Any:
    if key in _CACHE:
        return _CACHE[key]
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is None:
        fallback = DEFAULTS.get(key, (default, None))[0]
        return fallback if default is None else default
    try:
        value = json.loads(row.value)
    except json.JSONDecodeError:
        value = row.value
    _CACHE[key] = value
    return value


def set_value(db: Session, key: str, value: Any) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    payload = json.dumps(value)
    if row is None:
        db.add(Setting(key=key, value=payload))
    else:
        row.value = payload
    db.commit()
    _CACHE[key] = value


def all_settings(db: Session) -> dict[str, Any]:
    return {key: get(db, key) for key in DEFAULTS}


def invalidate() -> None:
    _CACHE.clear()
