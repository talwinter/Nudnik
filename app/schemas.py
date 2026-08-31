"""Request and response shapes."""
from datetime import datetime

from pydantic import BaseModel, Field


class StageIn(BaseModel):
    offset_minutes: int = 0
    label: str = ""
    kind: str = "prep"
    # Optional per-stage overrides. These MUST be declared: pydantic drops
    # undeclared keys, so omitting them here silently discarded whatever the
    # user set in the editor and the stage quietly kept the event's time.
    at_time: str | None = None
    intensity: str | None = None


class ReminderIn(BaseModel):
    title: str
    notes: str | None = None
    category: str = "general"
    emoji: str = ""
    priority: str = "normal"
    anchor_at: datetime
    all_day: bool = False
    tz: str | None = None
    repeat_kind: str = "none"
    repeat_interval: int = 1
    repeat_weekdays: str | None = None
    anchor_to_completion: bool = False
    repeat_until: datetime | None = None
    repeat_count: int | None = None
    stages: list[StageIn] = Field(default_factory=list)
    intensity: str = "relentless"
    channels: list[str] = Field(default_factory=list)
    ignore_quiet_hours: bool = False
    contact_phone: str | None = None
    contact_url: str | None = None
    require_confirmation: bool = False
    escalate_to_buddy: bool = False
    active: bool = True


class ReminderPatch(BaseModel):
    title: str | None = None
    notes: str | None = None
    category: str | None = None
    emoji: str | None = None
    priority: str | None = None
    anchor_at: datetime | None = None
    all_day: bool | None = None
    repeat_kind: str | None = None
    repeat_interval: int | None = None
    repeat_weekdays: str | None = None
    anchor_to_completion: bool | None = None
    repeat_until: datetime | None = None
    repeat_count: int | None = None
    stages: list[StageIn] | None = None
    intensity: str | None = None
    channels: list[str] | None = None
    ignore_quiet_hours: bool | None = None
    contact_phone: str | None = None
    contact_url: str | None = None
    require_confirmation: bool | None = None
    escalate_to_buddy: bool | None = None
    active: bool | None = None


class OccurrenceOut(BaseModel):
    id: int
    reminder_id: int
    cycle: int
    stage_index: int
    stage_label: str | None
    stage_kind: str
    due_at: datetime
    status: str
    snooze_until: datetime | None
    snooze_count: int
    attempts: int
    tier: int
    last_attempt_at: datetime | None
    next_attempt_at: datetime | None
    done_at: datetime | None
    done_via: str | None

    class Config:
        from_attributes = True


class ReminderOut(BaseModel):
    id: int
    title: str
    notes: str | None
    category: str
    emoji: str
    priority: str
    anchor_at: datetime
    all_day: bool
    tz: str | None
    repeat_kind: str
    repeat_interval: int
    repeat_weekdays: str | None
    anchor_to_completion: bool
    repeat_until: datetime | None
    repeat_count: int | None
    cycles_done: int
    stages: list = []
    intensity: str
    channels: list = []
    ignore_quiet_hours: bool
    contact_phone: str | None
    contact_url: str | None
    require_confirmation: bool
    escalate_to_buddy: bool
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SnoozeIn(BaseModel):
    preset: str | None = None
    minutes: int | None = None


class DoneIn(BaseModel):
    answer: str | None = None


class PushSubIn(BaseModel):
    endpoint: str
    keys: dict
    label: str | None = None


class QuickAddIn(BaseModel):
    text: str
    preset: str | None = None
    dry_run: bool = False


class SettingsPatch(BaseModel):
    values: dict


class TestChannelIn(BaseModel):
    channel: str
