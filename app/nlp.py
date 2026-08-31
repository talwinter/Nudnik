"""Quick-add parsing for Hebrew and English.

Deliberately rule-based: no model, no network, no API key. It handles the
phrasings people actually type into a reminder box and leaves everything else
as the title. Hebrew dual forms (יומיים, שבועיים, חודשיים) are handled
explicitly because they are extremely common and mean "two", not "some".

Returns a dict that maps straight onto the reminder create payload.
"""
import re
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

HE_MONTHS = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6,
    "יולי": 7, "אוגוסט": 8, "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
}
EN_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

# Python weekday(): Monday=0 .. Sunday=6
HE_WEEKDAYS = {
    "ראשון": 6, "שני": 0, "שלישי": 1, "רביעי": 2, "חמישי": 3, "שישי": 4, "שבת": 5,
}
EN_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

HE_NUMBERS = {
    "אחד": 1, "אחת": 1, "שניים": 2, "שתיים": 2, "שני": 2, "שתי": 2, "שלושה": 3,
    "שלוש": 3, "ארבעה": 4, "ארבע": 4, "חמישה": 5, "חמש": 5, "שישה": 6, "שש": 6,
    "שבעה": 7, "שבע": 7, "שמונה": 8, "תשעה": 9, "תשע": 9, "עשרה": 10, "עשר": 10,
}
EN_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "a": 1, "an": 1,
}

# Dual forms carry their own count.
HE_DUALS = {
    "יומיים": ("daily", 2), "שבועיים": ("weekly", 2),
    "חודשיים": ("monthly", 2), "שנתיים": ("yearly", 2),
}

HE_UNITS = {
    "דקה": "minutes", "דקות": "minutes", "שעה": "hours", "שעות": "hours",
    "יום": "days", "ימים": "days", "שבוע": "weeks", "שבועות": "weeks",
    "חודש": "months", "חודשים": "months", "שנה": "years", "שנים": "years",
}
EN_UNITS = {
    "minute": "minutes", "minutes": "minutes", "min": "minutes", "mins": "minutes",
    "hour": "hours", "hours": "hours", "hr": "hours", "hrs": "hours",
    "day": "days", "days": "days", "week": "weeks", "weeks": "weeks",
    "month": "months", "months": "months", "year": "years", "years": "years",
}

UNIT_TO_REPEAT = {
    "minutes": "hourly", "hours": "hourly", "days": "daily",
    "weeks": "weekly", "months": "monthly", "years": "yearly",
}

TIME_OF_DAY = {
    "בבוקר": 9, "בצהריים": 13, "אחהצ": 16, "אחר הצהריים": 16, "בערב": 20,
    "בלילה": 22, "morning": 9, "noon": 13, "afternoon": 16, "evening": 20, "night": 22,
}

NOISE_PREFIXES = [
    # Deliberately no "...ל" variants: stripping "תזכיר לי ל" would eat the
    # infinitive prefix of the verb that follows, leaving "התקשר" where the
    # user wrote "להתקשר".
    "תזכיר לי", "תזכורת", "אני צריך", "צריך", "לא לשכוח",
    "remind me to", "remind me", "reminder to", "reminder",
    "i need to", "need to", "don't forget to", "dont forget to",
]


def _strip_noise(text: str) -> str:
    lowered = text.strip()
    for prefix in sorted(NOISE_PREFIXES, key=len, reverse=True):
        if lowered.lower().startswith(prefix):
            return lowered[len(prefix):].strip(" ,:-")
    return lowered


def _cut(text: str, match: re.Match) -> str:
    return (text[: match.start()] + " " + text[match.end():]).strip()


def _apply_time(dt: datetime, hour: int, minute: int = 0) -> datetime:
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse(text: str, now: datetime | None = None, default_hour: int = 9) -> dict:
    """Parse free text into reminder fields.

    ``now`` must be local time; the caller converts the result to UTC.
    """
    now = now or datetime.now()
    original = text.strip()
    working = _strip_noise(original)

    result: dict = {
        "title": working,
        "when": None,
        "repeat_kind": "none",
        "repeat_interval": 1,
        "has_time": False,
        "confidence": 0.0,
    }

    explicit_hour: int | None = None
    explicit_minute = 0

    # --- explicit clock time: "ב-14:30", "at 14:30", "ב9" ---
    m = re.search(r"(?:\bב[-\s]?|\bat\s+|\b)(\d{1,2}):(\d{2})", working)
    if m:
        explicit_hour, explicit_minute = int(m.group(1)), int(m.group(2))
        working = _cut(working, m)
        result["has_time"] = True
    else:
        m = re.search(r"\bב[-\s]?(\d{1,2})\b(?!\s*(?:ב|/|\.|\-))", working)
        if m and 0 <= int(m.group(1)) <= 23:
            explicit_hour = int(m.group(1))
            working = _cut(working, m)
            result["has_time"] = True

    # --- named time of day ---
    for word, hour in TIME_OF_DAY.items():
        if word in working.lower():
            if explicit_hour is None:
                explicit_hour = hour
                result["has_time"] = True
            working = re.sub(re.escape(word), " ", working, flags=re.IGNORECASE).strip()
            break

    hour = explicit_hour if explicit_hour is not None else default_hour
    target: datetime | None = None

    # --- recurrence: "כל יומיים", "כל 3 שבועות", "every 2 months" ---
    for dual, (kind, count) in HE_DUALS.items():
        m = re.search(r"\bכל\s+" + dual, working)
        if m:
            result["repeat_kind"] = kind
            result["repeat_interval"] = count
            working = _cut(working, m)
            break

    if result["repeat_kind"] == "none":
        # The count group must be followed by real whitespace. Written as
        # "(count)?\s*(unit)" the engine happily splits one word across both
        # groups -- "כל יום" becomes count="יו", unit="ם" -- and the unit is
        # then never recognised.
        m = re.search(
            r"\b(?:כל|every)\s+(?:(\d+|[א-ת]+|[a-z]+)\s+)?([א-ת]+|[a-z]+)\b",
            working,
            re.IGNORECASE,
        )
        if m:
            count_raw, unit_raw = m.group(1), m.group(2).lower()
            unit = HE_UNITS.get(unit_raw) or EN_UNITS.get(unit_raw)
            if unit:
                count = 1
                if count_raw:
                    if count_raw.isdigit():
                        count = int(count_raw)
                    else:
                        count = HE_NUMBERS.get(count_raw) or EN_NUMBERS.get(count_raw.lower()) or 1
                result["repeat_kind"] = UNIT_TO_REPEAT[unit]
                result["repeat_interval"] = count
                working = _cut(working, m)

    # --- relative: "בעוד שבועיים", "in 3 days" ---
    for dual, (_kind, count) in HE_DUALS.items():
        m = re.search(r"\bבעוד\s+" + dual, working)
        if m:
            unit = {"יומיים": "days", "שבועיים": "weeks", "חודשיים": "months", "שנתיים": "years"}[dual]
            target = _apply_time(now + relativedelta(**{unit: count}), hour, explicit_minute)
            working = _cut(working, m)
            break

    if target is None:
        m = re.search(
            r"\b(?:בעוד|in)\s+(\d+|[א-ת]+|[a-z]+)\s*([א-ת]+|[a-z]+)", working, re.IGNORECASE
        )
        if m:
            count_raw, unit_raw = m.group(1), m.group(2).lower()
            unit = HE_UNITS.get(unit_raw) or EN_UNITS.get(unit_raw)
            if unit:
                count = (
                    int(count_raw)
                    if count_raw.isdigit()
                    else (HE_NUMBERS.get(count_raw) or EN_NUMBERS.get(count_raw.lower()) or 1)
                )
                base = now + relativedelta(**{unit: count})
                target = base if unit in ("minutes", "hours") else _apply_time(base, hour, explicit_minute)
                working = _cut(working, m)

    # --- named days ---
    if target is None:
        for word, delta in (("מחרתיים", 2), ("מחר", 1), ("היום", 0),
                            ("tomorrow", 1), ("today", 0)):
            m = re.search(r"\b" + word + r"\b", working, re.IGNORECASE)
            if m:
                target = _apply_time(now + timedelta(days=delta), hour, explicit_minute)
                working = _cut(working, m)
                break

    # --- weekday: "ביום ראשון", "on sunday" ---
    if target is None:
        for name, idx in {**HE_WEEKDAYS, **EN_WEEKDAYS}.items():
            m = re.search(r"(?:ביום\s+|יום\s+|on\s+|\b)" + name + r"\b", working, re.IGNORECASE)
            if m:
                ahead = (idx - now.weekday()) % 7
                ahead = ahead or 7  # "on Sunday" said on a Sunday means next one
                target = _apply_time(now + timedelta(days=ahead), hour, explicit_minute)
                working = _cut(working, m)
                break

    # --- absolute date: "ב-9 בספטמבר", "September 9", "9.9", "9/9/2026" ---
    #
    # The optional leading "ב-" is part of the date phrase and must be consumed
    # with it, or a stray ב is left dangling on the end of the title.
    if target is None:
        day = month = None
        m = re.search(
            r"(?:\bב[-\s]?)?\b(\d{1,2})\s*(?:ב|of\s+)?([א-ת]{3,}|[a-z]{3,})\b",
            working,
            re.IGNORECASE,
        )
        if m:
            candidate_month = HE_MONTHS.get(m.group(2)) or EN_MONTHS.get(m.group(2).lower())
            if candidate_month:
                day, month = int(m.group(1)), candidate_month
            else:
                m = None
        if m is None:
            # English writes the month first: "September 9".
            m = re.search(r"\b([a-z]{3,})\s+(\d{1,2})\b", working, re.IGNORECASE)
            if m:
                candidate_month = EN_MONTHS.get(m.group(1).lower())
                if candidate_month:
                    day, month = int(m.group(2)), candidate_month
                else:
                    m = None

        if m and month and 1 <= day <= 31:
            year = now.year + (1 if (month, day) < (now.month, now.day) else 0)
            try:
                target = _apply_time(datetime(year, month, day), hour, explicit_minute)
                working = _cut(working, m)
            except ValueError:
                target = None

    if target is None:
        m = re.search(
            r"(?:\bב[-\s]?)?\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", working
        )
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            year = int(m.group(3)) if m.group(3) else now.year
            if year < 100:
                year += 2000
            if 1 <= month <= 12 and 1 <= day <= 31:
                if not m.group(3) and (month, day) < (now.month, now.day):
                    year += 1
                try:
                    target = _apply_time(datetime(year, month, day), hour, explicit_minute)
                    working = _cut(working, m)
                except ValueError:
                    target = None

    # A bare time with no date means the next occurrence of that time.
    if target is None and result["has_time"]:
        candidate = _apply_time(now, hour, explicit_minute)
        target = candidate if candidate > now else candidate + timedelta(days=1)

    if target is None and result["repeat_kind"] != "none":
        target = _apply_time(now + timedelta(days=1), hour, explicit_minute)

    title = re.sub(r"\s{2,}", " ", working).strip(" ,.-:؛;")
    title = re.sub(r"^(את|the)\s+", "", title, flags=re.IGNORECASE).strip()

    result["title"] = title or original
    result["when"] = target
    result["confidence"] = round(
        (0.5 if target else 0.0)
        + (0.2 if result["has_time"] else 0.0)
        + (0.2 if result["repeat_kind"] != "none" else 0.0)
        + (0.1 if title else 0.0),
        2,
    )
    return result


EXAMPLES_HE = [
    "לקחת תרופה ב-9 בספטמבר כל חודשיים",
    "להתקשר למרפאה מחר בבוקר",
    "לשלם ארנונה בעוד שבועיים",
    "טסט לרכב ב-15.3 ב-8:30",
    "להוציא את הזבל כל יום ב-20:00",
]
EXAMPLES_EN = [
    "take medicine on september 9 every 2 months",
    "call the clinic tomorrow morning",
    "pay the bill in two weeks",
    "car inspection 15/3 at 8:30",
]
