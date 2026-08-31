"""Stage overrides must survive the API, not just the engine.

The engine handled per-stage time and intensity correctly while the API was
silently discarding both, because the pydantic schema did not declare them.
Everything looked right in the editor and the reminder still fired at the
event's time. This pins that shut.

Run against a running instance:  python scripts/test_api_stages.py [base_url]
"""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
DAY = 1440
IL = ZoneInfo("Asia/Jerusalem")
UTC = ZoneInfo("UTC")
failures = []


def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{extra}]" if extra else ""))
    if not cond:
        failures.append(label)


def local(iso: str):
    return datetime.fromisoformat(iso).replace(tzinfo=UTC).astimezone(IL)


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=30)

    payload = {
        "title": "לקנות SKYRIZI 360",
        "emoji": "💊",
        "category": "health",
        "anchor_at": "2026-09-09T16:00:00Z",     # 19:00 Israel
        "tz": "Asia/Jerusalem",
        "repeat_kind": "weekly",
        "repeat_interval": 8,
        "intensity": "relentless",
        "stages": [
            {"offset_minutes": -14 * DAY, "kind": "prep", "at_time": "10:00",
             "label": "להתקשר לבית מרקחת"},
            {"offset_minutes": -5 * DAY, "kind": "prep", "at_time": "09:00",
             "intensity": "gentle", "label": "לשים לב"},
            {"offset_minutes": 0, "kind": "main", "label": "להזריק"},
        ],
    }

    print("\n=== 1. Create ===")
    r = c.post("/api/reminders", json=payload)
    check("accepted", r.status_code < 300, f"{r.status_code} {r.text[:100]}")
    rid = r.json()["id"]

    stages = c.get(f"/api/reminders/{rid}").json()["stages"]
    check("at_time kept on the pharmacy stage", stages[0].get("at_time") == "10:00",
          str(stages[0].get("at_time")))
    check("at_time kept on the awareness stage", stages[1].get("at_time") == "09:00",
          str(stages[1].get("at_time")))
    check("intensity kept on the awareness stage", stages[1].get("intensity") == "gentle",
          str(stages[1].get("intensity")))
    check("main stage left clean", "at_time" not in stages[2])

    print("\n=== 2. Occurrences honour them, every cycle ===")
    occ = c.get("/api/occurrences", params={"status": "all", "limit": 80}).json()
    mine = sorted([o for o in occ if o["reminder_id"] == rid], key=lambda o: o["due_at"])
    for o in mine[:6]:
        print(f"    {local(o['due_at']):%d/%m/%Y %H:%M}  {o['stage_label']}")

    by_stage = lambda i: [o for o in mine if o["stage_index"] == i]  # noqa: E731
    check("pharmacy call always 10:00",
          all(local(o["due_at"]).strftime("%H:%M") == "10:00" for o in by_stage(0)),
          ",".join(local(o["due_at"]).strftime("%H:%M") for o in by_stage(0)))
    check("awareness always 09:00",
          all(local(o["due_at"]).strftime("%H:%M") == "09:00" for o in by_stage(1)),
          ",".join(local(o["due_at"]).strftime("%H:%M") for o in by_stage(1)))
    check("injection always 19:00 (no DST drift)",
          all(local(o["due_at"]).strftime("%H:%M") == "19:00" for o in by_stage(2)),
          ",".join(local(o["due_at"]).strftime("%H:%M") for o in by_stage(2)))

    print("\n=== 3. Editing a stage time moves the future occurrences ===")
    stages[0]["at_time"] = "11:30"
    r = c.patch(f"/api/reminders/{rid}", json={"stages": stages})
    check("edit accepted", r.status_code < 300, f"{r.status_code} {r.text[:100]}")

    occ2 = c.get("/api/occurrences", params={"status": "all", "limit": 80}).json()
    calls = sorted(
        [o for o in occ2 if o["reminder_id"] == rid and o["stage_index"] == 0],
        key=lambda o: o["due_at"],
    )
    # An occurrence that is already due is deliberately left alone -- it may
    # already be mid-escalation. Only genuinely future ones are re-timed, so
    # filter on the due date rather than on status.
    now_utc = datetime.now(UTC)
    future = [o for o in calls
              if datetime.fromisoformat(o["due_at"]).replace(tzinfo=UTC) > now_utc]
    past = [o for o in calls if o not in future]
    check("future pharmacy calls re-timed to 11:30",
          future and all(local(o["due_at"]).strftime("%H:%M") == "11:30" for o in future),
          ",".join(local(o["due_at"]).strftime("%H:%M") for o in future))
    check("an already-due occurrence is not disturbed",
          all(local(o["due_at"]).strftime("%H:%M") == "10:00" for o in past),
          ",".join(local(o["due_at"]).strftime("%H:%M") for o in past) or "none")
    check("edit preserved the intensity override",
          c.get(f"/api/reminders/{rid}").json()["stages"][1].get("intensity") == "gentle")

    c.delete(f"/api/reminders/{rid}")
    print("\n" + "=" * 58)
    if failures:
        print(f"FAILED {len(failures)}")
        return 1
    print("Stage overrides survive the API intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
