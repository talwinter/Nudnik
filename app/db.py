"""Database models.

The central idea: a **Reminder** is a definition, an **Occurrence** is one
concrete thing that must be acknowledged. The old design marked a reminder
``is_sent`` and moved on, which is precisely why a dismissed notification
vanished forever. Here, delivery is only ever recorded in ``NotificationLog``;
an Occurrence closes when, and only when, a human marks it done or skipped.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    future=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def utcnow() -> datetime:
    """Naive UTC. Stored naive so SQLite and Postgres behave identically."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Reminder(Base):
    """A thing that must eventually happen, plus how hard to chase it."""

    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    notes = Column(Text)
    category = Column(String(50), default="general")
    emoji = Column(String(16), default="")
    priority = Column(String(20), default="normal")  # low | normal | high | critical

    # The real-world moment. Lead-time stages are offsets from this.
    anchor_at = Column(DateTime, nullable=False)
    all_day = Column(Boolean, default=False)
    tz = Column(String(64), default="Asia/Jerusalem")

    # Recurrence. ``after_done`` anchors the next cycle to the completion date
    # rather than the schedule -- the correct model for "every 2 months" of a
    # medicine you might take a few days late.
    repeat_kind = Column(String(20), default="none")
    repeat_interval = Column(Integer, default=1)
    repeat_weekdays = Column(String(20))  # csv of 0-6, Monday=0, weekly only
    # True => the next cycle is measured from when you actually finished,
    # not from the calendar. Correct for "every 2 months" of a medicine you
    # might take three days late.
    anchor_to_completion = Column(Boolean, default=False)
    repeat_until = Column(DateTime)
    repeat_count = Column(Integer)
    cycles_done = Column(Integer, default=0)

    # [{"offset_minutes": -20160, "label": "...", "kind": "prep"}, ...]
    stages = Column(JSON, default=list)

    intensity = Column(String(20), default="relentless")
    channels = Column(JSON, default=list)  # empty list = use global default
    ignore_quiet_hours = Column(Boolean, default=False)

    # Removes the friction that makes a task get dodged: the phone number or
    # link you need in order to actually do the thing.
    contact_phone = Column(String(60))
    contact_url = Column(String(500))

    require_confirmation = Column(Boolean, default=False)
    escalate_to_buddy = Column(Boolean, default=False)

    active = Column(Boolean, default=True)
    archived_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    occurrences = relationship(
        "Occurrence",
        back_populates="reminder",
        cascade="all, delete-orphan",
        order_by="Occurrence.due_at",
    )


class Occurrence(Base):
    """One concrete open loop. Closes only on an explicit human action."""

    __tablename__ = "occurrences"

    id = Column(Integer, primary_key=True)
    reminder_id = Column(Integer, ForeignKey("reminders.id", ondelete="CASCADE"), nullable=False)

    cycle = Column(Integer, default=0)
    stage_index = Column(Integer, default=0)
    stage_label = Column(String(300))
    stage_kind = Column(String(20), default="main")  # prep | main | followup

    due_at = Column(DateTime, nullable=False)

    # scheduled -> active -> (snoozed) -> done | skipped | missed
    status = Column(String(20), default="scheduled")

    snooze_until = Column(DateTime)
    snooze_count = Column(Integer, default=0)

    # The nag tally. Surfaced in the UI as tick marks, because seeing that a
    # task has asked you nine times is itself the intervention.
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime)
    next_attempt_at = Column(DateTime)
    tier = Column(Integer, default=0)

    done_at = Column(DateTime)
    done_via = Column(String(40))
    confirm_answer = Column(String(20))

    created_at = Column(DateTime, default=utcnow)

    reminder = relationship("Reminder", back_populates="occurrences")
    logs = relationship(
        "NotificationLog", back_populates="occurrence", cascade="all, delete-orphan"
    )


Index("ix_occ_due_status", Occurrence.status, Occurrence.due_at)
Index("ix_occ_next_attempt", Occurrence.next_attempt_at)


class NotificationLog(Base):
    """Every delivery attempt, so "why didn't I get notified?" has an answer."""

    __tablename__ = "notification_log"

    id = Column(Integer, primary_key=True)
    occurrence_id = Column(
        Integer, ForeignKey("occurrences.id", ondelete="CASCADE"), nullable=True
    )
    channel = Column(String(30), nullable=False)
    tier = Column(Integer, default=0)
    status = Column(String(20), default="ok")  # ok | failed | skipped
    detail = Column(Text)
    created_at = Column(DateTime, default=utcnow, index=True)

    occurrence = relationship("Occurrence", back_populates="logs")


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    user_agent = Column(String(400))
    label = Column(String(120))
    created_at = Column(DateTime, default=utcnow)
    last_ok_at = Column(DateTime)
    failures = Column(Integer, default=0)


class ActionToken(Base):
    """One-tap done/snooze links for channels that cannot run JavaScript."""

    __tablename__ = "action_tokens"

    token = Column(String(64), primary_key=True)
    occurrence_id = Column(Integer, ForeignKey("occurrences.id", ondelete="CASCADE"))
    action = Column(String(30), nullable=False)
    payload = Column(JSON)
    expires_at = Column(DateTime)
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(80), primary_key=True)
    value = Column(Text)


class Event(Base):
    """Audit trail for the admin console."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    kind = Column(String(50), nullable=False)
    summary = Column(String(500))
    meta = Column(JSON)
    created_at = Column(DateTime, default=utcnow, index=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def log_event(db, kind: str, summary: str, meta: dict | None = None) -> None:
    db.add(Event(kind=kind, summary=summary, meta=meta or {}))
