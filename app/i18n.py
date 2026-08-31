"""Server-side strings.

Only text that leaves the server lives here -- notification bodies, email
subjects, the ICS feed. The web UI carries its own dictionary in
``static/js/i18n.js`` so it can switch language without a round trip.
"""

STRINGS: dict[str, dict[str, str]] = {
    "app_name": {"he": "נודניק", "en": "Nudnik"},
    "tagline": {
        "he": "לא מרפה עד שסגרת",
        "en": "It does not let go until you close it",
    },
    "action_done": {"he": "✅ בוצע", "en": "✅ Done"},
    "action_snooze_1h": {"he": "⏰ עוד שעה", "en": "⏰ In an hour"},
    "action_snooze_eve": {"he": "🌙 הערב", "en": "🌙 This evening"},
    "action_snooze_tomorrow": {"he": "☀️ מחר בבוקר", "en": "☀️ Tomorrow morning"},
    "action_open": {"he": "פתח", "en": "Open"},
    "action_skip": {"he": "דלג הפעם", "en": "Skip this one"},
    "overdue_since": {"he": "פתוח כבר", "en": "Open for"},
    "asked_times": {"he": "ביקשתי ממך {n} פעמים", "en": "Asked you {n} times"},
    "asked_once": {"he": "התזכורת הראשונה", "en": "First reminder"},
    "due_now": {"he": "הגיע הזמן", "en": "It is time"},
    "due_in": {"he": "בעוד {t}", "en": "In {t}"},
    "still_open": {"he": "עדיין לא סגרת את זה", "en": "You still have not closed this"},
    "call_now": {"he": "📞 חייג", "en": "📞 Call"},
    "brief_title": {"he": "מה פתוח היום", "en": "What is open today"},
    "brief_empty": {"he": "הכל סגור. יום נקי.", "en": "Everything is closed. Clean day."},
    "brief_overdue": {"he": "באיחור", "en": "Overdue"},
    "brief_today": {"he": "היום", "en": "Today"},
    "brief_soon": {"he": "בקרוב", "en": "Coming up"},
    "weekly_title": {"he": "השבוע שלך", "en": "Your week ahead"},
    "buddy_subject": {
        "he": "{name} עדיין לא טיפל/ה בזה",
        "en": "{name} still has not handled this",
    },
    "buddy_body": {
        "he": "המשימה \"{title}\" פתוחה כבר {age} ולא נסגרה אחרי {n} תזכורות.",
        "en": "The task \"{title}\" has been open for {age} and is unclosed after {n} reminders.",
    },
    "confirm_question": {"he": "עשית את זה?", "en": "Did you do it?"},
    "yes": {"he": "כן", "en": "Yes"},
    "no": {"he": "לא", "en": "No"},
    "snoozed_until": {"he": "נדחה ל-{t}", "en": "Snoozed until {t}"},
    "marked_done": {"he": "סומן כבוצע", "en": "Marked done"},
    "marked_skipped": {"he": "דולג", "en": "Skipped"},
    "already_closed": {"he": "כבר סגור", "en": "Already closed"},
    "link_expired": {"he": "הקישור פג תוקף", "en": "This link has expired"},
    "test_title": {"he": "בדיקת ערוץ", "en": "Channel test"},
    "test_body": {
        "he": "אם קיבלת את זה, הערוץ עובד.",
        "en": "If you got this, the channel works.",
    },
    "stage_prep": {"he": "הכנה", "en": "Prep"},
    "stage_main": {"he": "האירוע", "en": "The event"},
    "stage_followup": {"he": "מעקב", "en": "Follow-up"},
    "unit_minute": {"he": "דקות", "en": "minutes"},
    "unit_hour": {"he": "שעות", "en": "hours"},
    "unit_day": {"he": "ימים", "en": "days"},
    "unit_week": {"he": "שבועות", "en": "weeks"},
    "unit_month": {"he": "חודשים", "en": "months"},
}


def t(key: str, lang: str = "he", **fmt) -> str:
    entry = STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get("he") or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text
    return text


def humanise_delta(minutes: int, lang: str = "he") -> str:
    """A rough, readable duration. Used in notification bodies."""
    minutes = int(abs(minutes))
    if minutes < 60:
        return f"{minutes} {t('unit_minute', lang)}"
    if minutes < 60 * 36:
        hours = round(minutes / 60)
        return f"{hours} {t('unit_hour', lang)}"
    if minutes < 60 * 24 * 14:
        days = round(minutes / (60 * 24))
        return f"{days} {t('unit_day', lang)}"
    if minutes < 60 * 24 * 60:
        weeks = round(minutes / (60 * 24 * 7))
        return f"{weeks} {t('unit_week', lang)}"
    months = round(minutes / (60 * 24 * 30))
    return f"{months} {t('unit_month', lang)}"
