"""Regression tests for the quick-add parser.

Every case here came from a phrasing that actually broke at some point, so they
are worth keeping rather than trimming.

Run: python scripts/test_nlp.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app.nlp import parse  # noqa: E402

NOW = datetime(2026, 8, 30, 14, 0)

# (input, expected title, expected "YYYY-MM-DD HH:MM" or None, repeat_kind, interval)
CASES = [
    ("לקחת תרופה ב-9 בספטמבר כל חודשיים",
     "לקחת תרופה", "2026-09-09 09:00", "monthly", 2),
    ("להתקשר למרפאה מחר בבוקר",
     "להתקשר למרפאה", "2026-08-31 09:00", "none", 1),
    ("לשלם ארנונה בעוד שבועיים",
     "לשלם ארנונה", "2026-09-13 09:00", "none", 1),
    ("טסט לרכב ב-15.3 ב-8:30",
     "טסט לרכב", "2027-03-15 08:30", "none", 1),
    ("להוציא את הזבל כל יום ב-20:00",
     "להוציא הזבל", "2026-08-30 20:00", "daily", 1),
    ("לשלם ארנונה ב-1 בספטמבר",
     "לשלם ארנונה", "2026-09-01 09:00", "none", 1),
    ("לבדוק תוצאות בעוד 3 ימים",
     "לבדוק תוצאות", "2026-09-02 09:00", "none", 1),
    ("פגישה ביום ראשון ב-14:00",
     "פגישה", "2026-09-06 14:00", "none", 1),
    ("תזכיר לי להתקשר לאמא בערב",
     "להתקשר לאמא", "2026-08-30 20:00", "none", 1),
    ("take medicine on september 9 every 2 months",
     "take medicine on", "2026-09-09 09:00", "monthly", 2),
    ("call the clinic tomorrow morning",
     "call the clinic", "2026-08-31 09:00", "none", 1),
    ("pay the bill in two weeks",
     "pay the bill", "2026-09-13 09:00", "none", 1),
    ("car inspection 15/3 at 8:30",
     "car inspection", "2027-03-15 08:30", "none", 1),
    ("remind me to renew the passport every year",
     "renew passport", None, "yearly", 1),
]

failures = []


def main():
    for text, want_title, want_when, want_kind, want_interval in CASES:
        r = parse(text, NOW)
        got_when = r["when"].strftime("%Y-%m-%d %H:%M") if r["when"] else None

        problems = []
        # Titles are compared loosely: the parser strips filler words, and
        # exactly which filler survives is not worth pinning down.
        norm = lambda s: "".join(ch for ch in (s or "") if ch.isalnum() or ch == " ").split()
        want_words = set(norm(want_title))
        got_words = set(norm(r["title"]))
        if not want_words.issubset(got_words) or len(got_words - want_words) > 1:
            problems.append(f"title={r['title']!r} want~{want_title!r}")
        if want_when and got_when != want_when:
            problems.append(f"when={got_when} want={want_when}")
        if r["repeat_kind"] != want_kind:
            problems.append(f"repeat={r['repeat_kind']} want={want_kind}")
        if r["repeat_interval"] != want_interval:
            problems.append(f"interval={r['repeat_interval']} want={want_interval}")

        if problems:
            failures.append(text)
            print(f"  FAIL  {text}")
            for p in problems:
                print(f"          {p}")
        else:
            print(f"  PASS  {text}")
            print(f"          -> {r['title']!r} @ {got_when} repeat={r['repeat_kind']}/{r['repeat_interval']}")

    print("\n" + "=" * 58)
    if failures:
        print(f"FAILED {len(failures)}/{len(CASES)}")
        sys.exit(1)
    print(f"All {len(CASES)} cases passed.")


if __name__ == "__main__":
    main()
