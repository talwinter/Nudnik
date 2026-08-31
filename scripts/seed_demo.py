"""Populate a running instance with realistic data.

Useful for looking at the UI in a lived-in state rather than empty. Safe to run
against a fresh database; do not run it against real data.

    python scripts/seed_demo.py [base_url]
"""
import sys
from datetime import datetime, timedelta

import httpx

# Windows consoles default to cp1252, which cannot print emoji or Hebrew.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
DAY = 1440


def iso(dt):
    return dt.replace(microsecond=0).isoformat() + "Z"


def main():
    now = datetime.utcnow()
    items = [
        {
            "title": "לקחת את התרופה",
            "emoji": "💊", "category": "health", "priority": "high",
            "anchor_at": iso((now + timedelta(days=10)).replace(hour=9, minute=0)),
            "repeat_kind": "monthly", "repeat_interval": 2,
            "anchor_to_completion": True, "intensity": "relentless",
            "contact_phone": "03-6100000",
            "notes": "מרשם 4471. לבקש מד\"ר לוי חידוש אם נגמר.",
            "require_confirmation": True,
            "stages": [
                {"offset_minutes": -14 * DAY, "label": "להתקשר למרפאה ולהזמין את התרופה", "kind": "prep"},
                {"offset_minutes": -3 * DAY, "label": "לוודא שהתרופה הגיעה ולאסוף", "kind": "prep"},
                {"offset_minutes": 0, "label": "לקחת את התרופה", "kind": "main"},
            ],
        },
        {
            "title": "טסט לרכב",
            "emoji": "🚗", "category": "car", "priority": "high",
            "anchor_at": iso((now + timedelta(days=38)).replace(hour=8, minute=30)),
            "repeat_kind": "yearly", "repeat_interval": 1, "intensity": "relentless",
            "stages": [
                {"offset_minutes": -30 * DAY, "label": "לחדש ביטוח חובה", "kind": "prep"},
                {"offset_minutes": -14 * DAY, "label": "לקבוע טיפול לפני טסט", "kind": "prep"},
                {"offset_minutes": 0, "label": "טסט", "kind": "main"},
            ],
        },
        {
            "title": "לחזור לרואה החשבון",
            "emoji": "📞", "category": "work", "priority": "normal",
            "anchor_at": iso(now - timedelta(days=4, hours=2)),
            "repeat_kind": "none", "intensity": "relentless",
            "contact_phone": "052-5551234",
            "stages": [{"offset_minutes": 0, "label": "", "kind": "main"}],
        },
        {
            "title": "תום אחריות על המקרר",
            "emoji": "🛡️", "category": "money", "priority": "normal",
            "anchor_at": iso((now + timedelta(days=21)).replace(hour=10, minute=0)),
            "repeat_kind": "none", "intensity": "normal",
            "notes": "חשבונית בתיקייה. יש רעש מהמדחס — לבדוק לפני שנגמר.",
            "stages": [
                {"offset_minutes": -14 * DAY, "label": "לבדוק אם צריך תיקון תחת אחריות", "kind": "prep"},
                {"offset_minutes": 0, "label": "האחריות נגמרת", "kind": "main"},
            ],
        },
        {
            "title": "לשלם ארנונה",
            "emoji": "🧾", "category": "money", "priority": "high",
            "anchor_at": iso((now + timedelta(days=2)).replace(hour=12, minute=0)),
            "repeat_kind": "monthly", "repeat_interval": 2, "intensity": "normal",
            "stages": [{"offset_minutes": 0, "label": "", "kind": "main"}],
        },
        {
            "title": "בדיקות דם תקופתיות",
            "emoji": "🧪", "category": "health", "priority": "normal",
            "anchor_at": iso((now + timedelta(days=55)).replace(hour=7, minute=30)),
            "repeat_kind": "monthly", "repeat_interval": 6,
            "anchor_to_completion": True, "intensity": "normal",
            "stages": [
                {"offset_minutes": -10 * DAY, "label": "לבקש הפניה", "kind": "prep"},
                {"offset_minutes": -DAY, "label": "לצום מהערב", "kind": "prep"},
                {"offset_minutes": 0, "label": "בדיקות דם", "kind": "main"},
                {"offset_minutes": 7 * DAY, "label": "לבדוק תוצאות", "kind": "followup"},
            ],
        },
        {
            "title": "לחדש את הדרכון",
            "emoji": "🪪", "category": "bureaucracy", "priority": "high",
            "anchor_at": iso((now + timedelta(days=95)).replace(hour=9, minute=0)),
            "repeat_kind": "none", "intensity": "relentless",
            "escalate_to_buddy": True,
            "stages": [
                {"offset_minutes": -90 * DAY, "label": "לקבוע תור בלשכה", "kind": "prep"},
                {"offset_minutes": -30 * DAY, "label": "להכין תמונות ומסמכים", "kind": "prep"},
                {"offset_minutes": 0, "label": "התוקף נגמר", "kind": "main"},
            ],
        },
    ]

    with httpx.Client(base_url=BASE, timeout=30) as c:
        for item in items:
            r = c.post("/api/reminders", json=item)
            status = "ok" if r.status_code < 300 else f"FAIL {r.status_code} {r.text[:120]}"
            print(f"  {item['emoji']} {item['title']:<28} {status}")

        # Run the engine a few times so some loops carry a real nag tally.
        # The settings payload masks secrets; the reveal endpoint returns the
        # real key for the values that are meant to be copied.
        key = c.get("/api/settings/reveal", params={"key": "api_key"}).json()["value"]
        for _ in range(6):
            c.post(f"/api/tick?key={key}")
        print("\n  engine ticked; open loops now have delivery history")

        d = c.get("/api/dashboard").json()
        print(f"  overdue={len(d['overdue'])} today={len(d['today'])} upcoming={len(d['upcoming'])}")


if __name__ == "__main__":
    main()
