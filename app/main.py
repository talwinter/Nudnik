"""Application entry point."""
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import api, engine, nlp, scheduler, settings_store
from .config import STATIC_DIR
from .db import Occurrence, Reminder, SessionLocal, init_db, log_event, utcnow
from .i18n import t
from .recurrence import materialise, materialise_all, normalise_stages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("nudnik")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        settings_store.bootstrap(db)
        _ensure_vapid(db)
        created = materialise_all(db)
        if created:
            log.info("Materialised %s occurrence(s) on startup", created)
    finally:
        db.close()

    scheduler.start()
    log.info("Nudnik is up")
    yield
    scheduler.shutdown()


def _ensure_vapid(db: Session) -> None:
    """Generate a VAPID keypair on first run.

    These are *your* keys. Nothing is registered with anybody -- the keypair is
    the entire identity of this server as far as Web Push is concerned.
    """
    if settings_store.get(db, "vapid_public") and settings_store.get(db, "vapid_private"):
        return
    try:
        import base64

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.generate_private_key(ec.SECP256R1())
        private_der = key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_point = key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

        def b64(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).decode().rstrip("=")

        # pywebpush accepts a DER private key in url-safe base64.
        settings_store.set_value(db, "vapid_private", b64(private_der))
        settings_store.set_value(db, "vapid_public", b64(public_point))
        log.info("Generated a VAPID keypair for Web Push")
    except Exception:  # noqa: BLE001
        log.exception("Could not generate VAPID keys; push will stay disabled")


app = FastAPI(title="Nudnik", version="2.0.0", lifespan=lifespan)
app.include_router(api.router)


# --------------------------------------------------------------------------
# One-tap action links
# --------------------------------------------------------------------------

ACTION_PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #141019; color: #F2EDF7;
    font-family: Assistant, -apple-system, Segoe UI, Roboto, sans-serif;
    direction: {dir}; text-align: center; padding: 24px;
  }}
  .card {{ max-width: 420px; }}
  .mark {{
    width: 76px; height: 76px; border-radius: 50%; margin: 0 auto 20px;
    display: grid; place-items: center; font-size: 34px;
    background: {accent}22; border: 2px solid {accent};
  }}
  h1 {{ font-size: 26px; margin: 0 0 8px; font-weight: 700; }}
  p {{ color: #9C90A8; margin: 0 0 26px; font-size: 16px; line-height: 1.5; }}
  a {{
    display: inline-block; padding: 13px 26px; border-radius: 11px;
    background: #241D2D; color: #F2EDF7; text-decoration: none; font-weight: 600;
    border: 1px solid #382E42;
  }}
</style>
<div class="card">
  <div class="mark">{icon}</div>
  <h1>{heading}</h1>
  <p>{detail}</p>
  <a href="{home}">{cta}</a>
</div>
"""


def _action_page(lang: str, icon: str, accent: str, heading: str, detail: str, home: str) -> HTMLResponse:
    return HTMLResponse(
        ACTION_PAGE.format(
            title=heading,
            dir="rtl" if lang == "he" else "ltr",
            icon=icon,
            accent=accent,
            heading=heading,
            detail=detail,
            home=home or "/",
            cta=t("action_open", lang),
        )
    )


@app.get("/a/{token}", response_class=HTMLResponse)
def handle_action(token: str, db: Session = Depends(api.get_db)):
    """Close or postpone a loop straight from a notification, no app needed."""
    from . import security

    lang = settings_store.get(db, "lang", "he")
    home = settings_store.get(db, "public_url", "").rstrip("/") or "/"

    row = security.redeem(db, token)
    if row is None:
        return _action_page(
            lang, "⌛", "#9C90A8", t("link_expired", lang), "", home
        )

    occ = db.get(Occurrence, row.occurrence_id)
    if occ is None:
        return _action_page(lang, "❓", "#9C90A8", t("link_expired", lang), "", home)

    label = occ.stage_label or (occ.reminder.title if occ.reminder else "")

    if occ.status in ("done", "skipped") and row.action in ("done", "skip"):
        return _action_page(lang, "✅", "#5FD3A8", t("already_closed", lang), label, home)

    payload = row.payload or {}
    if row.action == "done":
        engine.mark_done(db, occ, via="link")
        row.used_at = utcnow()
        db.commit()
        return _action_page(lang, "✅", "#5FD3A8", t("marked_done", lang), label, home)

    if row.action == "skip":
        engine.mark_skipped(db, occ, via="link")
        row.used_at = utcnow()
        db.commit()
        return _action_page(lang, "⏭️", "#9C90A8", t("marked_skipped", lang), label, home)

    if row.action == "snooze":
        until = engine.snooze(
            db,
            occ,
            preset=payload.get("preset"),
            minutes=payload.get("minutes"),
            via="link",
        )
        local = engine.to_local(db, until).strftime("%d/%m %H:%M")
        # Snooze links stay reusable so a second tap postpones again.
        return _action_page(
            lang, "⏰", "#F5B544", t("snoozed_until", lang, t=local), label, home
        )

    raise HTTPException(400, "Unknown action")


# --------------------------------------------------------------------------
# Inbound Telegram -- add reminders by texting the bot
# --------------------------------------------------------------------------


@app.post("/hooks/telegram/{secret}")
def telegram_webhook(secret: str, update: dict = Body(...), db: Session = Depends(api.get_db)):
    """Create a reminder from a Telegram message.

    The secret in the path is the API key, which is how Telegram webhooks are
    normally authenticated -- there is no header to set.
    """
    expected = settings_store.get(db, "api_key", "")
    if not expected or secret != expected:
        raise HTTPException(403, "Invalid webhook secret")

    message = update.get("message") or update.get("edited_message") or {}
    text = (message.get("text") or "").strip()
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if not text:
        return {"ok": True, "skipped": "no text"}

    from . import channels

    lang = settings_store.get(db, "lang", "he")

    # Learning the chat id by texting the bot beats copying it out of an API
    # response by hand.
    if text.lower() in ("/start", "/id"):
        settings_store.set_value(db, "telegram_chat_id", chat_id)
        settings_store.set_value(db, "telegram_enabled", True)
        db.commit()
        channels.send_telegram(
            db,
            channels.Message(
                title=t("app_name", lang),
                body=f"chat id: {chat_id}\n{t('tagline', lang)}",
                lang=lang,
            ),
            chat_id=chat_id,
        )
        return {"ok": True, "chat_id": chat_id}

    if text.startswith("/"):
        return {"ok": True, "skipped": "command"}

    tz = ZoneInfo(settings_store.get(db, "timezone", "Asia/Jerusalem"))
    now_local = datetime.now(tz).replace(tzinfo=None)
    parsed = nlp.parse(text, now_local)
    when_local = parsed["when"] or now_local.replace(hour=9, minute=0)
    anchor = when_local.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    rem = Reminder(
        title=parsed["title"],
        anchor_at=anchor,
        tz=str(tz),
        repeat_kind=parsed["repeat_kind"],
        repeat_interval=parsed["repeat_interval"],
        stages=normalise_stages([]),
        intensity=settings_store.get(db, "default_intensity", "relentless"),
    )
    db.add(rem)
    db.flush()
    materialise(db, rem)
    log_event(db, "created", rem.title, {"reminder_id": rem.id, "via": "telegram"})
    db.commit()

    channels.send_telegram(
        db,
        channels.Message(
            title=f"✅ {rem.title}",
            body=when_local.strftime("%d/%m/%Y %H:%M"),
            lang=lang,
        ),
        chat_id=chat_id,
    )
    return {"ok": True, "reminder_id": rem.id}


# --------------------------------------------------------------------------
# PWA plumbing
# --------------------------------------------------------------------------


def asset_version() -> str:
    """A short fingerprint of the front-end files.

    This is what makes updates actually land. Serving correct cache headers is
    not enough on its own: an already-installed service worker keeps handing
    out its own cached copy of app.js, so the very fix that would repair it can
    never arrive. Stamping the version into both the asset URLs and the service
    worker's own bytes breaks that deadlock -- new bytes for sw.js means the
    browser installs a new worker, which then claims the page and reloads it.
    """
    parts: list[str] = []
    for name in (
        "index.html", "sw.js",
        "css/app.css",
        "js/i18n.js", "js/api.js", "js/views.js", "js/app.js",
    ):
        f = STATIC_DIR / name
        if f.exists():
            stat = f.stat()
            parts.append(f"{name}:{int(stat.st_mtime)}:{stat.st_size}")
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:10]
    return digest


@app.get("/sw.js")
def service_worker():
    """Served from the root so its scope covers the whole origin.

    The version is injected rather than hard-coded, so every front-end change
    produces different worker bytes and triggers the browser's update check.
    """
    path = STATIC_DIR / "sw.js"
    if not path.exists():
        raise HTTPException(404, "Service worker not built")
    body = path.read_text(encoding="utf-8").replace("__VERSION__", asset_version())
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/api/version")
def app_version():
    return {"version": asset_version()}


@app.get("/manifest.webmanifest")
def manifest(db: Session = Depends(api.get_db)):
    lang = settings_store.get(db, "lang", "he")
    return JSONResponse(
        {
            "id": "/",
            "name": t("app_name", lang),
            "short_name": t("app_name", lang),
            "description": t("tagline", lang),
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#141019",
            "theme_color": "#141019",
            "lang": lang,
            "dir": "rtl" if lang == "he" else "ltr",
            "categories": ["productivity", "health"],
            "icons": [
                {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                {
                    "src": "/static/icons/icon-maskable.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
            "shortcuts": [
                {
                    "name": "פתוח עכשיו" if lang == "he" else "Open now",
                    "url": "/#/open",
                },
                {
                    "name": "הוספה מהירה" if lang == "he" else "Quick add",
                    "url": "/#/add",
                },
            ],
        },
        media_type="application/manifest+json",
    )


class CachedStatic(StaticFiles):
    """Static files with explicit caching rules.

    Without a Cache-Control header browsers apply *heuristic* caching, which
    silently serves a stale stylesheet for hours after a deploy -- and a
    service-worker fetch() goes through the same HTTP cache, so even a
    network-first worker cannot see the update. Fonts and icons are
    content-stable and get a long TTL; code must always revalidate.
    """

    IMMUTABLE_DIRS = ("/fonts/", "/icons/")

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        normalised = "/" + path.replace("\\", "/").lstrip("/")
        if any(part in normalised for part in self.IMMUTABLE_DIRS):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", CachedStatic(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    """The shell, with every asset URL version-stamped.

    index.html itself is never cached, so the browser always learns the current
    asset URLs; those URLs then change whenever the files do, which makes a
    stale stylesheet or script impossible regardless of what any cache holds.
    """
    path = STATIC_DIR / "index.html"
    if not path.exists():
        return HTMLResponse("<h1>Nudnik</h1><p>UI not built.</p>", status_code=500)
    body = path.read_text(encoding="utf-8").replace("__V__", asset_version())
    return HTMLResponse(body, headers={"Cache-Control": "no-cache"})


@app.get("/{path:path}", response_class=HTMLResponse)
def spa_fallback(path: str):
    """Single-page app: unknown paths render the shell and let the hash route."""
    if path.startswith(("api/", "static/", "a/", "hooks/")):
        raise HTTPException(404, "Not found")
    return index()
