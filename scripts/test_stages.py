"""Per-stage time, per-stage intensity, and daylight-saving stability.

The scenario is a real one: an injection at 19:00 every 8 weeks, a pharmacy
call two weeks earlier that has to land in business hours, and an
informational "the date is approaching" stage that should not be chased.

Run: python scripts/test_stages.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="nudnik-stages-"))
os.environ["DATABASE_URL"] = "sqlite:///" + os.environ["DATA_DIR"] + "/t.db"
os.environ["SCHEDULER_ENABLED"] = "false"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import engine, settings_store  # noqa: E402
from app.db import Occurrence, Reminder, SessionLocal, init_db, utcnow  # noqa: E402
from app.recurrence import materialise, normalise_stages  # noqa: E402

DAY = 1440
IL = ZoneInfo("Asia/Jerusalem")
UTC = ZoneInfo("UTC")
failures = []


def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{extra}]" if extra else ""))
    if not cond:
        failures.append(label)


def local(dt):
    return dt.replace(tzinfo=UTC).astimezone(IL)


def main() -> int:
    init_db()
    db = SessionLocal()
    settings_store.bootstrap(db)
    settings_store.set_value(db, "quiet_hours_enabled", False)
    settings_store.invalidate()

    anchor_utc = (
        datetime(2026, 9, 9, 19, 0).replace(tzinfo=IL).astimezone(UTC).replace(tzinfo=None)
    )
    rem = Reminder(
        title="לקנות SKYRIZI 360",
        anchor_at=anchor_utc,
        tz="Asia/Jerusalem",
        repeat_kind="weekly",
        repeat_interval=8,
        intensity="relentless",
        stages=normalise_stages([
            {"offset_minutes": -14 * DAY, "kind": "prep", "at_time": "10:00",
             "label": "להתקשר לבית מרקחת נאות גנים"},
            {"offset_minutes": -5 * DAY, "kind": "prep", "at_time": "09:00",
             "intensity": "gentle", "label": "לשים לב שהתאריך מתקרב"},
            {"offset_minutes": 0, "kind": "main", "label": "להזריק את התרופה"},
        ]),
    )
    db.add(rem)
    db.flush()
    materialise(db, rem)
    db.commit()

    occs = db.query(Occurrence).order_by(Occurrence.due_at).all()

    print("\n=== 1. Schedule in local time ===")
    for o in occs[:9]:
        print(f"    cycle {o.cycle}  {local(o.due_at):%d/%m/%Y  %H:%M}   {o.stage_label}")

    calls = [o for o in occs if o.stage_index == 0]
    aware = [o for o in occs if o.stage_index == 1]
    shots = [o for o in occs if o.stage_index == 2]

    print("\n=== 2. Stage times hold, every cycle ===")
    check("pharmacy call always at 10:00",
          all(local(o.due_at).strftime("%H:%M") == "10:00" for o in calls),
          ",".join(local(o.due_at).strftime("%H:%M") for o in calls))
    check("awareness nudge always at 09:00",
          all(local(o.due_at).strftime("%H:%M") == "09:00" for o in aware),
          ",".join(local(o.due_at).strftime("%H:%M") for o in aware))

    print("\n=== 3. Daylight saving does not move the injection ===")
    # Cycle 1 falls after Israel leaves daylight time; UTC arithmetic would
    # silently deliver it at 18:00 from then on.
    check("injection always at 19:00 across the DST change",
          all(local(o.due_at).strftime("%H:%M") == "19:00" for o in shots),
          ",".join(f"{local(o.due_at):%d/%m %H:%M}" for o in shots))

    print("\n=== 4. Gap between doses stays 56 days ===")
    gaps = [(shots[i + 1].due_at - shots[i].due_at).days for i in range(len(shots) - 1)]
    check("every gap is 56 days", all(g == 56 for g in gaps), str(gaps))

    print("\n=== 5. Per-stage intensity ===")
    check("pharmacy call inherits relentless",
          engine.profile_for(rem, calls[0]).key == "relentless")
    check("awareness stage overrides to gentle",
          engine.profile_for(rem, aware[0]).key == "gentle")
    check("injection inherits relentless",
          engine.profile_for(rem, shots[0]).key == "relentless")

    print("\n=== 6. Gentle stops chasing; relentless does not ===")
    now = utcnow()
    for o in (calls[0], aware[0]):
        o.due_at = now - timedelta(minutes=5)
        o.status = "active"
        o.next_attempt_at = o.due_at
    db.commit()

    for hours in (0, 3, 26, 100, 400):
        engine.tick(db, now=now + timedelta(hours=hours))
    db.refresh(calls[0])
    db.refresh(aware[0])
    print(f"    relentless attempts={calls[0].attempts}   gentle attempts={aware[0].attempts}")

    check("gentle stage stopped after its ladder", aware[0].attempts <= 3, str(aware[0].attempts))
    check("gentle stage is still OPEN, just quiet", aware[0].status == "active")
    check("relentless kept going", calls[0].attempts > aware[0].attempts)

    db.close()
    print("\n" + "=" * 58)
    if failures:
        print(f"FAILED {len(failures)}")
        return 1
    print("All stage behaviour verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
