"""Action tokens and API authentication.

Channels like email and Telegram cannot run JavaScript, so "Done" has to be a
plain URL. Those URLs carry a single-purpose random token bound to one
occurrence and one action -- not a signed blob of user input.
"""
import hmac
import secrets
import time
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
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


SESSION_COOKIE = "nudnik_session"
SESSION_MAX_AGE = 90 * 24 * 3600  # re-login quarterly


def _signer(db: Session) -> TimestampSigner:
    return TimestampSigner(settings_store.get(db, "secret_key", "") or "nudnik")


def issue_session(db: Session) -> str:
    """A signed, expiring session token. The password itself is never stored
    in the cookie, so a stolen cookie cannot be replayed as a credential."""
    return _signer(db).sign(b"admin").decode()


def valid_session(db: Session, token: str | None) -> bool:
    if not token:
        return False
    try:
        _signer(db).unsign(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def password_ok(candidate: str) -> bool:
    from .config import ADMIN_PASSWORD

    if not ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(str(candidate), str(ADMIN_PASSWORD))


# --------------------------------------------------------------------------
# Brute-force protection
# --------------------------------------------------------------------------
#
# The login page sits on a public URL, so without this a password can be
# attacked at whatever rate the network allows. Held in memory rather than the
# database: a restart clearing the counters is an acceptable trade for not
# writing a row on every failed guess, and an attacker cannot force a restart.

MAX_ATTEMPTS = 6
LOCKOUT_SECONDS = 900          # 15 minutes
ATTEMPT_WINDOW = 900

_failures: dict[str, list[float]] = {}


def _client_key(request: Request) -> str:
    """Identify the caller. Behind a tunnel the real address is forwarded."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def lockout_remaining(request: Request) -> int:
    """Seconds until this client may try again; 0 when it may try now."""
    key = _client_key(request)
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < ATTEMPT_WINDOW]
    _failures[key] = recent
    if len(recent) < MAX_ATTEMPTS:
        return 0
    return max(1, int(LOCKOUT_SECONDS - (now - recent[-1])))


def record_failure(request: Request) -> None:
    key = _client_key(request)
    _failures.setdefault(key, []).append(time.time())
    # Keep the map from growing without bound on a long-lived process.
    if len(_failures) > 2048:
        cutoff = time.time() - ATTEMPT_WINDOW
        for k in [k for k, v in _failures.items() if not v or v[-1] < cutoff]:
            _failures.pop(k, None)


def clear_failures(request: Request) -> None:
    _failures.pop(_client_key(request), None)


def auth_required() -> bool:
    """Whether this instance is protected at all.

    An empty ADMIN_PASSWORD leaves everything open. That is fine on a laptop
    and reckless behind a public tunnel, so the UI says so out loud.
    """
    from .config import ADMIN_PASSWORD

    return bool(ADMIN_PASSWORD)


def sanitise_next(value: str | None) -> str:
    """Only ever redirect to a same-site path."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
