"""Editing a reminder must move its whole chain, not just part of it.

Reported from real use: pick a template, get an anchor of "today", then correct
the date -- and the lead-time stages stayed on the old dates, nagging about a
schedule that no longer existed. Nothing could clear them, because resync only
deleted *future* scheduled rows and those ghosts were in the past.

Run: python scripts/test_edit_reschedule.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="nudnik-resched-"))
os.environ["DATABASE_URL"] = "sqlite:///" + os.environ["DATA_DIR"] + "/t.db"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ.pop("ADMIN_PASSWORD", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

UTC = ZoneInfo("UTC")
DAY = 1440
failures = []


def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{extra}]" if extra else ""))
    if not cond:
        failures.append(label)


def at(iso):
    # The API stores and returns naive UTC, so a string with no offset is UTC
    # rather than local. Python 3.10 also rejects a trailing Z outright.
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def offsets(rem):
    """Each occurrence's distance from the anchor, in days."""
    anchor = at(rem["anchor_at"])
    return sorted(
        round((at(o["due_at"]) - anchor).total_seconds() / 86400)
        for o in rem["occurrences"]
        if o["cycle"] == 0
    )


def main() -> int:
    with TestClient(app) as c:
        print("\n=== 1. A template with prep stages refuses to guess a date ===")
        r = c.post("/api/quick-add", json={"text": "לקנות SKYRIZI",
                                           "preset": "medicine_refill"})
        check("refused without a date", r.status_code == 422, str(r.status_code))
        check("and says why", "תאריך" in r.text or "date" in r.text.lower())

        print("\n=== 2. With an explicit date it is used verbatim ===")
        r = c.post("/api/quick-add", json={
            "text": "לקנות SKYRIZI", "preset": "medicine_refill",
            "anchor_at": "2026-09-09T16:00:00Z"})
        check("accepted", r.status_code == 200, str(r.status_code))
        rid = r.json()["id"]
        rem = c.get(f"/api/reminders/{rid}").json()
        check("anchor is the date given, not today",
              at(rem["anchor_at"]) == at("2026-09-09T16:00:00Z"),
              rem["anchor_at"])
        check("template's chain applied", offsets(rem) == [-14, -3, 0], str(offsets(rem)))

        print("\n=== 3. Moving the date moves the WHOLE chain ===")
        c.patch(f"/api/reminders/{rid}", json={"anchor_at": "2026-11-20T17:00:00Z"})
        rem = c.get(f"/api/reminders/{rid}").json()
        check("anchor moved", at(rem["anchor_at"]) == at("2026-11-20T17:00:00Z"))
        check("every stage moved with it", offsets(rem) == [-14, -3, 0], str(offsets(rem)))

        # The real symptom: nothing left behind on the old timetable.
        old_window = at("2026-09-09T16:00:00Z")
        strays = [o for o in rem["occurrences"]
                  if abs((at(o["due_at"]) - old_window).days) < 20]
        check("no occurrence left near the old date", not strays,
              ",".join(o["due_at"][:10] for o in strays))

        print("\n=== 4. Removing a stage removes its occurrences ===")
        keep = [s for s in rem["stages"] if s["offset_minutes"] != -3 * DAY]
        c.patch(f"/api/reminders/{rid}", json={"stages": keep})
        rem = c.get(f"/api/reminders/{rid}").json()
        check("the deleted stage is gone", offsets(rem) == [-14, 0], str(offsets(rem)))
        check("its occurrences went too",
              not any("הגיעה" in (o["stage_label"] or "") for o in rem["occurrences"]))

        print("\n=== 5. Closed occurrences are never rewritten ===")
        target = next(o for o in rem["occurrences"] if o["status"] == "scheduled")
        c.post(f"/api/occurrences/{target['id']}/done")
        before = c.get(f"/api/occurrences/{target['id']}").json()
        c.patch(f"/api/reminders/{rid}", json={"anchor_at": "2027-03-01T09:00:00Z"})
        after = c.get(f"/api/occurrences/{target['id']}").json()
        check("history keeps its status", after["status"] == "done", after["status"])
        check("history keeps its date", after["due_at"] == before["due_at"])

    print("\n" + "=" * 58)
    if failures:
        print(f"FAILED {len(failures)}")
        return 1
    print("Rescheduling verified: the chain moves as one, history stays put.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
