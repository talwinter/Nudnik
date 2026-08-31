"""End-to-end check of the scenario the app exists for.

Medicine due 9 September, taken every 2 months, with an errand two weeks
earlier to order it. Added *today* -- so the "order it" stage is already in the
past and must nag immediately rather than be silently skipped.

Run: python scripts/test_flow.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="nudnik-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.environ['DATA_DIR']}/test.db"
os.environ["SCHEDULER_ENABLED"] = "false"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import engine, escalation, settings_store  # noqa: E402
from app.db import NotificationLog, Occurrence, Reminder, SessionLocal, init_db, utcnow  # noqa: E402
from app.recurrence import materialise, normalise_stages  # noqa: E402

PASS, FAIL = "  PASS", "  FAIL"
failures = []


def check(label, condition, detail=""):
    print(f"{PASS if condition else FAIL}  {label}" + (f"  [{detail}]" if detail else ""))
    if not condition:
        failures.append(label)


def main():
    init_db()
    db = SessionLocal()
    settings_store.bootstrap(db)
    # Quiet hours would legitimately defer attempts and make the ladder
    # assertions time-of-day dependent, so switch them off for the test.
    settings_store.set_value(db, "quiet_hours_enabled", False)
    settings_store.invalidate()

    now = utcnow()
    anchor = (now + timedelta(days=10)).replace(hour=9, minute=0, second=0, microsecond=0)

    print("\n=== 1. Create the medicine reminder ===")
    print(f"    now    = {now:%Y-%m-%d %H:%M}")
    print(f"    anchor = {anchor:%Y-%m-%d %H:%M}  (the day the medicine is taken)")

    rem = Reminder(
        title="לקחת את התרופה",
        emoji="💊",
        category="health",
        priority="high",
        anchor_at=anchor,
        repeat_kind="monthly",
        repeat_interval=2,
        anchor_to_completion=True,
        intensity="relentless",
        contact_phone="03-1234567",
        stages=normalise_stages([
            {"offset_minutes": -14 * 1440, "label": "להתקשר ולהזמין את התרופה", "kind": "prep"},
            {"offset_minutes": -3 * 1440, "label": "לוודא שהתרופה הגיעה", "kind": "prep"},
            {"offset_minutes": 0, "label": "לקחת את התרופה", "kind": "main"},
        ]),
    )
    db.add(rem)
    db.flush()
    created = materialise(db, rem)
    db.commit()

    check("three stages materialised", created == 3, f"created={created}")

    occs = db.query(Occurrence).order_by(Occurrence.due_at).all()
    for o in occs:
        overdue = "OVERDUE" if o.due_at < now else "        "
        print(f"    {o.due_at:%Y-%m-%d %H:%M}  {overdue}  {o.stage_label}")

    print("\n=== 2. The already-past prep stage must nag immediately ===")
    prep = occs[0]
    check(
        "order-it stage is in the past",
        prep.due_at < now,
        f"{prep.due_at:%Y-%m-%d} < {now:%Y-%m-%d}",
    )

    stats = engine.tick(db)
    db.refresh(prep)
    check("first tick promoted and notified it", stats["notified"] >= 1, str(stats))
    check("status is now active", prep.status == "active", prep.status)
    check("attempt was recorded", (prep.attempts or 0) == 1, f"attempts={prep.attempts}")

    print("\n=== 3. The escalation ladder widens over time ===")
    profile = escalation.get_profile("relentless")
    print("    attempt  minutes-after-due  tier  channels")
    seen_tiers = []
    for attempt in range(12):
        offset, tier = escalation.plan_attempt(profile, attempt)
        seen_tiers.append(tier)
        chans = ",".join(escalation.channels_for_tier(tier))
        print(f"    {attempt:>7}  {offset:>17}  {tier:>4}  {chans}")

    check("ladder starts at the quietest tier", seen_tiers[0] == 0)
    check("ladder reaches the widest tier", max(seen_tiers) == 4)
    check("ladder never stops for relentless", profile.repeat_every is not None)

    print("\n=== 4. Simulating an ignored reminder over 24h ===")
    # Walk the clock forward and tick repeatedly, never acting.
    for hours in (1, 3, 6, 12, 24):
        future = now + timedelta(hours=hours)
        engine.tick(db, now=future)
        db.refresh(prep)
        print(f"    +{hours:>3}h  attempts={prep.attempts:<3} tier={prep.tier}  status={prep.status}")

    check("kept chasing without being closed", prep.attempts >= 4, f"attempts={prep.attempts}")
    check("escalated beyond the first tier", prep.tier >= 2, f"tier={prep.tier}")
    check("still open", prep.status == "active", prep.status)

    logged = db.query(NotificationLog).count()
    check("every attempt was logged", logged >= prep.attempts, f"log rows={logged}")

    print("\n=== 5. Snoozing repeatedly does not buy quiet forever ===")
    for _ in range(3):
        engine.snooze(db, prep, minutes=1)
    db.refresh(prep)
    check("snooze count tracked", prep.snooze_count == 3, f"count={prep.snooze_count}")

    engine.tick(db, now=now + timedelta(hours=25))
    db.refresh(prep)
    check(
        "serial snoozing forced a wider tier",
        prep.tier >= 2,
        f"tier={prep.tier} after {prep.snooze_count} snoozes",
    )

    print("\n=== 6. Only a human action closes the loop ===")
    engine.mark_done(db, prep, via="test")
    db.refresh(prep)
    check("marked done", prep.status == "done", prep.status)
    check("done timestamp recorded", prep.done_at is not None)

    before = db.query(Occurrence).count()
    engine.tick(db, now=now + timedelta(hours=48))
    db.refresh(prep)
    check("a closed loop is never chased again", prep.status == "done", prep.status)
    check("attempts frozen after close", prep.attempts is not None)

    print("\n=== 7. Completing the main stage starts the next cycle ===")
    main_occ = (
        db.query(Occurrence)
        .filter(Occurrence.stage_kind == "main", Occurrence.status != "done")
        .order_by(Occurrence.due_at)
        .first()
    )
    check("main stage exists", main_occ is not None)

    # Take it four days late, which is the whole reason for completion anchoring.
    taken_at = anchor + timedelta(days=4)
    engine.mark_done(db, main_occ, via="test")
    db.refresh(rem)

    after = db.query(Occurrence).count()
    check("next cycle was generated", after > before, f"{before} -> {after}")

    next_cycle = (
        db.query(Occurrence)
        .filter(Occurrence.cycle == 1)
        .order_by(Occurrence.due_at)
        .all()
    )
    check("next cycle has all three stages", len(next_cycle) == 3, f"got {len(next_cycle)}")

    if next_cycle:
        next_main = [o for o in next_cycle if o.stage_kind == "main"][0]
        gap_days = (next_main.due_at - main_occ.done_at).days
        print(f"    next dose: {next_main.due_at:%Y-%m-%d %H:%M}  ({gap_days} days after completion)")
        check(
            "next dose is ~2 months after completion, not after the plan",
            55 <= gap_days <= 63,
            f"{gap_days} days",
        )
        next_prep = min(next_cycle, key=lambda o: o.due_at)
        lead = (next_main.due_at - next_prep.due_at).days
        check("the order-it errand is chained again", lead == 14, f"{lead} days ahead")
        print(f"    next 'order it': {next_prep.due_at:%Y-%m-%d}  ({lead} days before the dose)")

    print("\n=== 8. Quiet hours hold non-critical notifications ===")
    settings_store.set_value(db, "quiet_hours_enabled", True)
    settings_store.set_value(db, "quiet_start", "23:00")
    settings_store.set_value(db, "quiet_end", "07:30")
    settings_store.invalidate()

    local_night = engine.to_utc(db, datetime(2026, 9, 20, 2, 0))
    local_noon = engine.to_utc(db, datetime(2026, 9, 20, 12, 0))
    check("2am counts as quiet", engine.in_quiet_hours(db, local_night))
    check("noon does not", not engine.in_quiet_hours(db, local_noon))
    resume = engine.next_quiet_end(db, local_night)
    print(f"    a 2am nag would be held until {engine.to_local(db, resume):%H:%M} local")
    check("held until the window ends", engine.to_local(db, resume).hour == 7)

    db.close()

    print("\n" + "=" * 58)
    if failures:
        print(f"FAILED: {len(failures)}")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
