"""Action tokens and API authentication.

Channels like email and Telegram cannot run JavaScript, so "Done" has to be a
plain URL. Those URLs carry a single-purpose random token bound to one
occurrence and one action -- not a signed blob of user input.
"""
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from . import settings_store
from .db import ActionToken, utcnow

TOKEN_TTL_DAYS = 45


def mint(db: Session, occurrence_id: int, action: str, payload: dict | None = None) -> str:
    """Create a one-tap action token. Reuses an unused token for the same pair
    so repeated notifications about one occurrence share a stable link."""
    existing = (
        db.query(ActionToken)
        .filter(
            ActionToken.occurrence_id == occurrence_id,
            ActionToken.action == action,
            ActionToken.used_at.is_(None),
            ActionToken.expires_at > utcnow(),
        )
        .first()
    )
    if existing:
        return existing.token

    token = secrets.token_urlsafe(24)
    db.add(
        ActionToken(
            token=token,
            occurrence_id=occurrence_id,
            action=action,
            payload=payload or {},
            expires_at=utcnow() + timedelta(days=TOKEN_TTL_DAYS),
        )
    )
    db.flush()
    return token


def redeem(db: Session, token: str) -> ActionToken | None:
    row = db.query(ActionToken).filter(ActionToken.token == token).first()
    if row is None:
        return None
    if row.expires_at and row.expires_at < utcnow():
        return None
    return row


def action_url(db: Session, occurrence_id: int, action: str, payload: dict | None = None) -> str:
    base = settings_store.get(db, "public_url", "").rstrip("/")
    token = mint(db, occurrence_id, action, payload)
    return f"{base}/a/{token}"


def require_api_key(db: Session, provided: str | None) -> None:
    expected = settings_store.get(db, "api_key", "")
    if not expected:
        raise HTTPException(status_code=503, detail="API key not configured")
    if not provided or not hmac.compare_digest(str(provided), str(expected)):
        raise HTTPException(status_code=401, detail="Invalid API key")


def api_key_dep(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str | None:
    return x_api_key


def check_admin(request: Request, db: Session) -> bool:
    """Admin gate.

    An empty ``ADMIN_PASSWORD`` means the instance is unprotected, which is
    fine behind a private tunnel and dangerous on the open internet -- the
    settings page says so out loud.
    """
    from .config import ADMIN_PASSWORD

    if not ADMIN_PASSWORD:
        return True
    session_pw = request.cookies.get("nudnik_admin")
    return bool(session_pw) and hmac.compare_digest(session_pw, ADMIN_PASSWORD)


def sanitise_next(value: str | None) -> str:
    """Only ever redirect to a same-site path."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
