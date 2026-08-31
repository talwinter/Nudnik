"""Delivery channels.

Every channel that can carry a button carries the same three: Done, Snooze, and
Open. Closing a loop must never require opening the app -- the friction of
"open the app, find the item, tap done" is exactly what turns a seen
notification into an ignored one.

Each sender returns ``(ok, detail)`` and never raises; the engine logs the
result so a silent failure is impossible to hide.
"""
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import httpx
from sqlalchemy.orm import Session

from . import security, settings_store
from .db import NotificationLog, PushSubscription, utcnow
from .i18n import t

TIMEOUT = httpx.Timeout(15.0, connect=8.0)


# --------------------------------------------------------------------------
# Message assembly
# --------------------------------------------------------------------------


class Message:
    """A notification rendered once and reused across every channel."""

    def __init__(
        self,
        title: str,
        body: str,
        *,
        occurrence_id: int | None = None,
        tier: int = 0,
        urgency: str = "normal",
        links: dict | None = None,
        contact_phone: str | None = None,
        contact_url: str | None = None,
        tally: int = 0,
        lang: str = "he",
    ):
        self.title = title
        self.body = body
        self.occurrence_id = occurrence_id
        self.tier = tier
        self.urgency = urgency
        self.links = links or {}
        self.contact_phone = contact_phone
        self.contact_url = contact_url
        self.tally = tally
        self.lang = lang


def build_links(db: Session, occurrence_id: int) -> dict:
    """One-tap URLs for channels without native action buttons."""
    base = settings_store.get(db, "public_url", "").rstrip("/")
    return {
        "done": security.action_url(db, occurrence_id, "done"),
        "snooze_1h": security.action_url(db, occurrence_id, "snooze", {"minutes": 60}),
        "snooze_evening": security.action_url(db, occurrence_id, "snooze", {"preset": "evening"}),
        "snooze_tomorrow": security.action_url(db, occurrence_id, "snooze", {"preset": "tomorrow"}),
        "skip": security.action_url(db, occurrence_id, "skip"),
        "open": f"{base}/#/occurrence/{occurrence_id}",
    }


# --------------------------------------------------------------------------
# Web Push
# --------------------------------------------------------------------------


def send_push(db: Session, msg: Message) -> tuple[bool, str]:
    if not settings_store.get(db, "push_enabled", True):
        return False, "disabled"
    public = settings_store.get(db, "vapid_public", "")
    private = settings_store.get(db, "vapid_private", "")
    if not public or not private:
        return False, "VAPID keys not configured"

    subs = db.query(PushSubscription).all()
    if not subs:
        return False, "no devices subscribed"

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return False, "pywebpush not installed"

    payload = json.dumps(
        {
            "title": msg.title,
            "body": msg.body,
            "occurrence_id": msg.occurrence_id,
            "tier": msg.tier,
            "urgency": msg.urgency,
            "tally": msg.tally,
            "lang": msg.lang,
            "links": msg.links,
            "phone": msg.contact_phone,
            "url": msg.links.get("open", "/"),
        },
        ensure_ascii=False,
    )

    subject = settings_store.get(db, "vapid_subject", "mailto:admin@localhost")
    ok_count = 0
    errors: list[str] = []

    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=private,
                vapid_claims={"sub": subject},
                # "high" tells the OS to wake the device rather than batch it.
                ttl=60 * 60 * 24,
                headers={"Urgency": "high" if msg.tier >= 2 else "normal"},
            )
            sub.last_ok_at = utcnow()
            sub.failures = 0
            ok_count += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            # 404/410 mean the browser threw the subscription away. Keeping a
            # dead endpoint would make every future send look half-failed.
            if status in (404, 410):
                db.delete(sub)
                errors.append(f"expired subscription removed ({status})")
            else:
                sub.failures = (sub.failures or 0) + 1
                errors.append(f"{status}: {exc}")
        except Exception as exc:  # noqa: BLE001 - never break the ladder
            errors.append(str(exc))

    if ok_count:
        return True, f"delivered to {ok_count} device(s)" + (
            f"; {len(errors)} failed" if errors else ""
        )
    return False, "; ".join(errors) or "no deliveries"


# --------------------------------------------------------------------------
# ntfy (self-hosted push)
# --------------------------------------------------------------------------


def send_ntfy(db: Session, msg: Message, priority: int = 4) -> tuple[bool, str]:
    if not settings_store.get(db, "ntfy_enabled", False):
        return False, "disabled"
    url = (settings_store.get(db, "ntfy_url", "") or "").rstrip("/")
    topic = settings_store.get(db, "ntfy_topic", "")
    if not url or not topic:
        return False, "ntfy url/topic not configured"

    actions = []
    if msg.links.get("done"):
        actions.append(f"http, {t('action_done', msg.lang)}, {msg.links['done']}, clear=true")
    if msg.links.get("snooze_1h"):
        actions.append(
            f"http, {t('action_snooze_1h', msg.lang)}, {msg.links['snooze_1h']}, clear=true"
        )
    if msg.contact_phone:
        actions.append(f"view, {t('call_now', msg.lang)}, tel:{msg.contact_phone}")
    elif msg.links.get("open"):
        actions.append(f"view, {t('action_open', msg.lang)}, {msg.links['open']}")

    headers = {
        "Title": msg.title,
        "Priority": str(priority),
        "Tags": "bell" if msg.tier < 2 else "rotating_light",
        "Markdown": "yes",
    }
    if actions:
        # ntfy caps at three actions per message.
        headers["Actions"] = "; ".join(actions[:3])
    token = settings_store.get(db, "ntfy_token", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"{url}/{topic}", content=msg.body.encode("utf-8"), headers=headers
            )
        if resp.status_code < 300:
            return True, f"ntfy {resp.status_code}"
        return False, f"ntfy {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------


def _telegram_keyboard(msg: Message) -> dict | None:
    rows = []
    first = []
    if msg.links.get("done"):
        first.append({"text": t("action_done", msg.lang), "url": msg.links["done"]})
    if msg.links.get("snooze_1h"):
        first.append({"text": t("action_snooze_1h", msg.lang), "url": msg.links["snooze_1h"]})
    if first:
        rows.append(first)

    second = []
    if msg.links.get("snooze_tomorrow"):
        second.append(
            {"text": t("action_snooze_tomorrow", msg.lang), "url": msg.links["snooze_tomorrow"]}
        )
    if msg.links.get("skip"):
        second.append({"text": t("action_skip", msg.lang), "url": msg.links["skip"]})
    if second:
        rows.append(second)

    third = []
    if msg.contact_phone:
        third.append({"text": t("call_now", msg.lang), "url": f"tel:{msg.contact_phone}"})
    if msg.contact_url:
        third.append({"text": "🔗", "url": msg.contact_url})
    if msg.links.get("open"):
        third.append({"text": t("action_open", msg.lang), "url": msg.links["open"]})
    if third:
        rows.append(third)

    return {"inline_keyboard": rows} if rows else None


def send_telegram(
    db: Session, msg: Message, chat_id: str | None = None
) -> tuple[bool, str]:
    if chat_id is None and not settings_store.get(db, "telegram_enabled", False):
        return False, "disabled"
    token = settings_store.get(db, "telegram_token", "")
    target = chat_id or settings_store.get(db, "telegram_chat_id", "")
    if not token or not target:
        return False, "telegram token/chat not configured"

    text = f"*{_md_escape(msg.title)}*\n{_md_escape(msg.body)}"
    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    keyboard = _telegram_keyboard(msg)
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage", json=payload
            )
        if resp.status_code == 200:
            return True, "sent"
        return False, f"{resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _md_escape(text: str) -> str:
    for ch in ("_", "*", "[", "]", "`"):
        text = text.replace(ch, "\\" + ch)
    return text


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------


EMAIL_CSS = (
    "font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;"
    "background:#141019;color:#F2EDF7;padding:28px;border-radius:14px"
)


def _email_html(msg: Message) -> str:
    rtl = msg.lang == "he"
    direction = "rtl" if rtl else "ltr"
    align = "right" if rtl else "left"

    def button(label: str, href: str, bg: str, fg: str = "#141019") -> str:
        return (
            f'<a href="{href}" style="display:inline-block;padding:12px 22px;'
            f"margin:4px;border-radius:10px;background:{bg};color:{fg};"
            f'text-decoration:none;font-weight:700;font-size:15px">{label}</a>'
        )

    buttons = ""
    if msg.links.get("done"):
        buttons += button(t("action_done", msg.lang), msg.links["done"], "#5FD3A8")
    if msg.links.get("snooze_tomorrow"):
        buttons += button(
            t("action_snooze_tomorrow", msg.lang), msg.links["snooze_tomorrow"], "#F5B544"
        )
    if msg.links.get("open"):
        buttons += button(t("action_open", msg.lang), msg.links["open"], "#332A3D", "#F2EDF7")

    tally = ""
    if msg.tally > 1:
        tally = (
            f'<p style="color:#FF5C7A;font-size:14px;margin:6px 0 0">'
            f"{t('asked_times', msg.lang, n=msg.tally)}</p>"
        )

    phone = ""
    if msg.contact_phone:
        phone = (
            f'<p style="margin:14px 0 0"><a href="tel:{msg.contact_phone}" '
            f'style="color:#5FD3A8;font-size:16px">{t("call_now", msg.lang)} '
            f"{msg.contact_phone}</a></p>"
        )

    return f"""<div dir="{direction}" style="{EMAIL_CSS};text-align:{align}">
<div style="font-size:13px;letter-spacing:.14em;color:#9C90A8;text-transform:uppercase">
{t('app_name', msg.lang)}</div>
<h1 style="font-size:24px;margin:10px 0 6px;color:#F2EDF7">{msg.title}</h1>
<p style="font-size:16px;line-height:1.6;color:#C9BFD4;margin:0">{msg.body}</p>
{tally}{phone}
<div style="margin-top:22px">{buttons}</div>
<p style="margin-top:26px;font-size:12px;color:#6F6579">
{t('tagline', msg.lang)}</p>
</div>"""


def send_email(db: Session, msg: Message, to: str | None = None) -> tuple[bool, str]:
    if to is None and not settings_store.get(db, "email_enabled", False):
        return False, "disabled"
    host = settings_store.get(db, "smtp_host", "")
    port = int(settings_store.get(db, "smtp_port", 587) or 587)
    user = settings_store.get(db, "smtp_user", "")
    password = settings_store.get(db, "smtp_pass", "")
    recipient = to or settings_store.get(db, "email_to", "") or user
    if not host or not recipient:
        return False, "SMTP not configured"

    mail = MIMEMultipart("alternative")
    mail["From"] = formataddr((t("app_name", msg.lang), user or f"nudnik@{host}"))
    mail["To"] = recipient
    mail["Subject"] = msg.title
    mail.attach(MIMEText(f"{msg.title}\n\n{msg.body}\n\n{msg.links.get('done','')}", "plain", "utf-8"))
    mail.attach(MIMEText(_email_html(msg), "html", "utf-8"))

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        with server:
            if port != 465 and settings_store.get(db, "smtp_tls", True):
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(user or f"nudnik@{host}", [recipient], mail.as_string())
        return True, f"sent to {recipient}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# --------------------------------------------------------------------------
# Generic webhook -- the escape hatch to Home Assistant, n8n, Discord, Slack
# --------------------------------------------------------------------------


def send_webhook(db: Session, msg: Message) -> tuple[bool, str]:
    if not settings_store.get(db, "webhook_enabled", False):
        return False, "disabled"
    url = settings_store.get(db, "webhook_url", "")
    if not url:
        return False, "webhook url not configured"
    method = (settings_store.get(db, "webhook_method", "POST") or "POST").upper()
    headers = settings_store.get(db, "webhook_headers", {}) or {}

    body = {
        "title": msg.title,
        "body": msg.body,
        "occurrence_id": msg.occurrence_id,
        "tier": msg.tier,
        "urgency": msg.urgency,
        "attempts": msg.tally,
        "links": msg.links,
        "phone": msg.contact_phone,
        # Discord and Slack both read a plain "content"/"text" field, so a raw
        # webhook URL from either works with no extra mapping.
        "content": f"**{msg.title}**\n{msg.body}",
        "text": f"*{msg.title}*\n{msg.body}",
    }

    # A body template lets this one channel speak any third-party API's shape
    # -- GreenAPI, Home Assistant, a self-hosted gateway -- without each one
    # needing its own integration. Values are JSON-escaped before substitution,
    # so a quote or newline inside a reminder title cannot break the payload.
    template = settings_store.get(db, "webhook_template", "")
    if template:
        fields = {
            "title": msg.title,
            "body": msg.body,
            "text": msg.title + "\n" + msg.body,
            "done_url": msg.links.get("done", ""),
            "snooze_url": msg.links.get("snooze_tomorrow", ""),
            "open_url": msg.links.get("open", ""),
            "phone": msg.contact_phone or "",
            "attempts": str(msg.tally),
            "occurrence_id": str(msg.occurrence_id or ""),
        }
        rendered = template
        for key, value in fields.items():
            escaped = json.dumps(str(value))[1:-1]
            rendered = rendered.replace("{{" + key + "}}", escaped)
        try:
            body = json.loads(rendered)
        except json.JSONDecodeError as exc:
            return False, f"webhook template is not valid JSON: {exc}"

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.request(method, url, json=body, headers=headers)
        if resp.status_code < 300:
            return True, f"{method} {resp.status_code}"
        return False, f"{resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# --------------------------------------------------------------------------
# Twilio SMS / WhatsApp
# --------------------------------------------------------------------------


def _twilio_send(db: Session, from_: str, to: str, body: str) -> tuple[bool, str]:
    sid = settings_store.get(db, "twilio_sid", "")
    auth = settings_store.get(db, "twilio_auth", "")
    if not sid or not auth or not from_ or not to:
        return False, "Twilio not configured"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data={"From": from_, "To": to, "Body": body},
                auth=(sid, auth),
            )
        if resp.status_code in (200, 201):
            return True, "sent"
        return False, f"{resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def send_sms(db: Session, msg: Message) -> tuple[bool, str]:
    if not settings_store.get(db, "sms_enabled", False):
        return False, "disabled"
    body = f"{msg.title}\n{msg.body}\n{msg.links.get('done', '')}"
    return _twilio_send(
        db,
        settings_store.get(db, "twilio_from", ""),
        settings_store.get(db, "twilio_to", ""),
        body,
    )


def send_whatsapp(db: Session, msg: Message) -> tuple[bool, str]:
    if not settings_store.get(db, "whatsapp_enabled", False):
        return False, "disabled"
    body = f"*{msg.title}*\n{msg.body}\n\n{t('action_done', msg.lang)}: {msg.links.get('done', '')}"
    return _twilio_send(
        db,
        settings_store.get(db, "whatsapp_from", ""),
        settings_store.get(db, "whatsapp_to", ""),
        body,
    )



# --------------------------------------------------------------------------
# Gotify (self-hosted, alternative to ntfy)
# --------------------------------------------------------------------------


def send_gotify(db: Session, msg: Message) -> tuple[bool, str]:
    if not settings_store.get(db, "gotify_enabled", False):
        return False, "disabled"
    url = (settings_store.get(db, "gotify_url", "") or "").rstrip("/")
    token = settings_store.get(db, "gotify_token", "")
    if not url or not token:
        return False, "gotify url/token not configured"

    body = msg.body
    if msg.links.get("done"):
        body += "\n\n" + t("action_done", msg.lang) + ": " + msg.links["done"]

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"{url}/message",
                params={"token": token},
                json={
                    "title": msg.title,
                    "message": body,
                    # Gotify priority 8+ triggers its high-priority alert.
                    "priority": 5 + min(msg.tier, 3),
                    "extras": {
                        "client::notification": {"click": {"url": msg.links.get("open", "")}}
                    },
                },
            )
        if resp.status_code < 300:
            return True, f"gotify {resp.status_code}"
        return False, f"gotify {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# --------------------------------------------------------------------------
# Matrix (self-hosted Synapse, or any homeserver)
# --------------------------------------------------------------------------


def send_matrix(db: Session, msg: Message) -> tuple[bool, str]:
    if not settings_store.get(db, "matrix_enabled", False):
        return False, "disabled"
    homeserver = (settings_store.get(db, "matrix_homeserver", "") or "").rstrip("/")
    token = settings_store.get(db, "matrix_token", "")
    room = settings_store.get(db, "matrix_room", "")
    if not homeserver or not token or not room:
        return False, "matrix homeserver/token/room not configured"

    links = ""
    if msg.links.get("done"):
        links = (
            f'<br/><a href="{msg.links["done"]}">{t("action_done", msg.lang)}</a>'
            f' &nbsp; <a href="{msg.links.get("snooze_tomorrow", "")}">'
            f'{t("action_snooze_tomorrow", msg.lang)}</a>'
        )

    import urllib.parse

    room_enc = urllib.parse.quote(room, safe="")
    txn = f"nudnik{utcnow().timestamp()}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.put(
                f"{homeserver}/_matrix/client/v3/rooms/{room_enc}/send/m.room.message/{txn}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "msgtype": "m.text",
                    "body": msg.title + "\n" + msg.body,
                    "format": "org.matrix.custom.html",
                    "formatted_body": f"<b>{msg.title}</b><br/>{msg.body}{links}",
                },
            )
        if resp.status_code < 300:
            return True, f"matrix {resp.status_code}"
        return False, f"matrix {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------

SENDERS = {
    "push": send_push,
    "ntfy": send_ntfy,
    "telegram": send_telegram,
    "email": send_email,
    "webhook": send_webhook,
    "sms": send_sms,
    "whatsapp": send_whatsapp,
    "gotify": send_gotify,
    "matrix": send_matrix,
}

ALL_CHANNELS = list(SENDERS)


def dispatch(
    db: Session,
    channel: str,
    msg: Message,
    *,
    log: bool = True,
    ntfy_priority: int = 4,
) -> tuple[bool, str]:
    sender = SENDERS.get(channel)
    if sender is None:
        return False, f"unknown channel {channel}"

    if channel == "ntfy":
        ok, detail = sender(db, msg, ntfy_priority)
    else:
        ok, detail = sender(db, msg)

    if log:
        db.add(
            NotificationLog(
                occurrence_id=msg.occurrence_id,
                channel=channel,
                tier=msg.tier,
                status="ok" if ok else ("skipped" if detail == "disabled" else "failed"),
                detail=detail[:1000],
            )
        )
    return ok, detail


def configured_channels(db: Session) -> dict[str, bool]:
    """Which channels are actually usable right now. Drives the admin UI."""
    subs = db.query(PushSubscription).count()
    return {
        "push": bool(
            settings_store.get(db, "push_enabled", True)
            and settings_store.get(db, "vapid_public", "")
            and subs
        ),
        "ntfy": bool(
            settings_store.get(db, "ntfy_enabled", False)
            and settings_store.get(db, "ntfy_topic", "")
        ),
        "telegram": bool(
            settings_store.get(db, "telegram_enabled", False)
            and settings_store.get(db, "telegram_token", "")
            and settings_store.get(db, "telegram_chat_id", "")
        ),
        "email": bool(
            settings_store.get(db, "email_enabled", False)
            and settings_store.get(db, "smtp_host", "")
        ),
        "webhook": bool(
            settings_store.get(db, "webhook_enabled", False)
            and settings_store.get(db, "webhook_url", "")
        ),
        "sms": bool(
            settings_store.get(db, "sms_enabled", False)
            and settings_store.get(db, "twilio_sid", "")
        ),
        "whatsapp": bool(
            settings_store.get(db, "whatsapp_enabled", False)
            and settings_store.get(db, "twilio_sid", "")
        ),
        "gotify": bool(
            settings_store.get(db, "gotify_enabled", False)
            and settings_store.get(db, "gotify_token", "")
        ),
        "matrix": bool(
            settings_store.get(db, "matrix_enabled", False)
            and settings_store.get(db, "matrix_room", "")
        ),
    }
