"""Runtime configuration.

Environment variables provide *defaults*. Anything an operator may reasonably
want to change at runtime lives in the ``settings`` table instead, so the admin
UI can rewire channels without a redeploy. See ``app.settings_store``.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'nudnik.db'}")

# Public origin, used to build action links that land in email/Telegram/ntfy.
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8080").rstrip("/")

SECRET_KEY = os.getenv("SECRET_KEY", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Asia/Jerusalem")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "he")

SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() in ("1", "true", "yes")
TICK_SECONDS = int(os.getenv("TICK_SECONDS", "30"))

# How far ahead occurrences are materialised. Keeps the calendar view honest
# without generating an unbounded number of rows for daily reminders.
HORIZON_DAYS = int(os.getenv("HORIZON_DAYS", "180"))

# Occurrences are only chased for this long before being marked missed, so a
# reminder created and abandoned years ago cannot resurrect itself.
GIVE_UP_DAYS = int(os.getenv("GIVE_UP_DAYS", "30"))
