"""Reminder templates.

Each preset is a ready-made stage chain. The point is that the hard part of a
recurring obligation is rarely the event itself -- it is the errand two weeks
earlier that makes the event possible. Presets encode that chain so you do not
have to remember to build it.

``offset_minutes`` is relative to the anchor: negative is before.
"""

DAY = 24 * 60

PRESETS: list[dict] = [
    {
        "key": "medicine_refill",
        "emoji": "💊",
        "category": "health",
        "name": {"he": "תרופה חוזרת", "en": "Recurring medicine"},
        "description": {
            "he": "תרופה שנלקחת כל כמה חודשים, כולל התזכורת להזמין אותה מראש",
            "en": "A medicine taken every few months, including the errand to order it in time",
        },
        "priority": "high",
        "intensity": "relentless",
        "repeat_kind": "monthly",
        "repeat_interval": 2,
        "anchor_to_completion": True,
        "require_confirmation": True,
        "stages": [
            {
                "offset_minutes": -14 * DAY,
                "kind": "prep",
                "label": {
                    "he": "להתקשר למרפאה ולהזמין את התרופה",
                    "en": "Call the clinic and order the medicine",
                },
            },
            {
                "offset_minutes": -3 * DAY,
                "kind": "prep",
                "label": {
                    "he": "לוודא שהתרופה הגיעה ולאסוף",
                    "en": "Confirm the medicine arrived and collect it",
                },
            },
            {
                "offset_minutes": 0,
                "kind": "main",
                "label": {"he": "לקחת את התרופה", "en": "Take the medicine"},
            },
        ],
    },
    {
        "key": "doctor_appointment",
        "emoji": "🩺",
        "category": "health",
        "name": {"he": "תור לרופא", "en": "Doctor appointment"},
        "description": {
            "he": "כולל הכנה יום לפני והפניה מראש",
            "en": "Includes the referral errand and a day-before nudge",
        },
        "priority": "high",
        "intensity": "normal",
        "repeat_kind": "none",
        "stages": [
            {
                "offset_minutes": -7 * DAY,
                "kind": "prep",
                "label": {"he": "לסדר הפניה והתחייבות", "en": "Sort out the referral"},
            },
            {
                "offset_minutes": -DAY,
                "kind": "prep",
                "label": {"he": "מחר יש תור — לאשר הגעה", "en": "Appointment tomorrow — confirm"},
            },
            {"offset_minutes": 0, "kind": "main", "label": {"he": "התור", "en": "The appointment"}},
        ],
    },
    {
        "key": "blood_test",
        "emoji": "🧪",
        "category": "health",
        "name": {"he": "בדיקות דם תקופתיות", "en": "Periodic blood test"},
        "priority": "normal",
        "intensity": "normal",
        "repeat_kind": "monthly",
        "repeat_interval": 6,
        "anchor_to_completion": True,
        "stages": [
            {
                "offset_minutes": -10 * DAY,
                "kind": "prep",
                "label": {"he": "לבקש הפניה לבדיקות", "en": "Request the lab referral"},
            },
            {
                "offset_minutes": -DAY,
                "kind": "prep",
                "label": {"he": "לצום מהערב", "en": "Start fasting tonight"},
            },
            {"offset_minutes": 0, "kind": "main", "label": {"he": "בדיקות דם", "en": "Blood test"}},
            {
                "offset_minutes": 7 * DAY,
                "kind": "followup",
                "label": {"he": "לבדוק תוצאות", "en": "Check the results"},
            },
        ],
    },
    {
        "key": "car_test",
        "emoji": "🚗",
        "category": "car",
        "name": {"he": "טסט לרכב", "en": "Vehicle inspection"},
        "description": {
            "he": "טסט שנתי, כולל ביטוח חובה וטיפול לפני",
            "en": "Annual inspection, including insurance and pre-service",
        },
        "priority": "high",
        "intensity": "relentless",
        "repeat_kind": "yearly",
        "repeat_interval": 1,
        "stages": [
            {
                "offset_minutes": -30 * DAY,
                "kind": "prep",
                "label": {"he": "לחדש ביטוח חובה", "en": "Renew compulsory insurance"},
            },
            {
                "offset_minutes": -14 * DAY,
                "kind": "prep",
                "label": {"he": "לקבוע טיפול לפני טסט", "en": "Book the pre-inspection service"},
            },
            {
                "offset_minutes": -3 * DAY,
                "kind": "prep",
                "label": {"he": "לקבוע תור לטסט", "en": "Book the inspection slot"},
            },
            {"offset_minutes": 0, "kind": "main", "label": {"he": "טסט", "en": "Inspection"}},
        ],
    },
    {
        "key": "warranty_expiry",
        "emoji": "🛡️",
        "category": "money",
        "name": {"he": "תום אחריות", "en": "Warranty expiry"},
        "description": {
            "he": "להספיק לתקן או להאריך לפני שהאחריות נגמרת",
            "en": "Repair or extend before the cover runs out",
        },
        "priority": "normal",
        "intensity": "normal",
        "repeat_kind": "none",
        "stages": [
            {
                "offset_minutes": -30 * DAY,
                "kind": "prep",
                "label": {
                    "he": "לבדוק אם משהו צריך תיקון תחת אחריות",
                    "en": "Check whether anything needs fixing under warranty",
                },
            },
            {
                "offset_minutes": -7 * DAY,
                "kind": "prep",
                "label": {"he": "שבוע אחרון לאחריות", "en": "Final week of cover"},
            },
            {
                "offset_minutes": 0,
                "kind": "main",
                "label": {"he": "האחריות נגמרת היום", "en": "Warranty ends today"},
            },
        ],
    },
    {
        "key": "subscription_renewal",
        "emoji": "🔁",
        "category": "money",
        "name": {"he": "חידוש מנוי", "en": "Subscription renewal"},
        "description": {
            "he": "להחליט אם ממשיכים לפני שמחייבים",
            "en": "Decide before they charge you",
        },
        "priority": "normal",
        "intensity": "normal",
        "repeat_kind": "yearly",
        "repeat_interval": 1,
        "stages": [
            {
                "offset_minutes": -10 * DAY,
                "kind": "prep",
                "label": {
                    "he": "להחליט אם ממשיכים או מבטלים",
                    "en": "Decide: keep it or cancel",
                },
            },
            {
                "offset_minutes": 0,
                "kind": "main",
                "label": {"he": "המנוי מתחדש היום", "en": "Renews today"},
            },
        ],
    },
    {
        "key": "document_renewal",
        "emoji": "🪪",
        "category": "bureaucracy",
        "name": {"he": "חידוש מסמך", "en": "Document renewal"},
        "description": {
            "he": "דרכון, רישיון נהיגה, תעודת זהות",
            "en": "Passport, driving licence, ID card",
        },
        "priority": "high",
        "intensity": "relentless",
        "repeat_kind": "none",
        "stages": [
            {
                "offset_minutes": -90 * DAY,
                "kind": "prep",
                "label": {"he": "לקבוע תור בלשכה", "en": "Book the government appointment"},
            },
            {
                "offset_minutes": -30 * DAY,
                "kind": "prep",
                "label": {"he": "להכין מסמכים ותמונות", "en": "Prepare documents and photos"},
            },
            {
                "offset_minutes": 0,
                "kind": "main",
                "label": {"he": "התוקף נגמר היום", "en": "Expires today"},
            },
        ],
    },
    {
        "key": "bill_payment",
        "emoji": "🧾",
        "category": "money",
        "name": {"he": "תשלום חשבון", "en": "Bill payment"},
        "priority": "high",
        "intensity": "relentless",
        "repeat_kind": "monthly",
        "repeat_interval": 1,
        "stages": [
            {
                "offset_minutes": -3 * DAY,
                "kind": "prep",
                "label": {"he": "לוודא שיש כיסוי בחשבון", "en": "Check the account has cover"},
            },
            {"offset_minutes": 0, "kind": "main", "label": {"he": "לשלם", "en": "Pay it"}},
        ],
    },
    {
        "key": "call_back",
        "emoji": "📞",
        "category": "personal",
        "name": {"he": "לחזור למישהו", "en": "Call someone back"},
        "description": {
            "he": "השיחה שאתה כל הזמן דוחה",
            "en": "The call you keep putting off",
        },
        "priority": "normal",
        "intensity": "relentless",
        "repeat_kind": "none",
        "stages": [
            {"offset_minutes": 0, "kind": "main", "label": {"he": "להתקשר", "en": "Make the call"}}
        ],
    },
    {
        "key": "blank",
        "emoji": "📌",
        "category": "general",
        "name": {"he": "תזכורת ריקה", "en": "Blank reminder"},
        "description": {"he": "להתחיל מאפס", "en": "Start from scratch"},
        "priority": "normal",
        "intensity": "relentless",
        "repeat_kind": "none",
        "stages": [{"offset_minutes": 0, "kind": "main", "label": {"he": "", "en": ""}}],
    },
]

CATEGORIES: list[dict] = [
    {"key": "health", "emoji": "💊", "he": "בריאות", "en": "Health"},
    {"key": "bureaucracy", "emoji": "🗂️", "he": "בירוקרטיה", "en": "Bureaucracy"},
    {"key": "car", "emoji": "🚗", "he": "רכב", "en": "Car"},
    {"key": "home", "emoji": "🏠", "he": "בית", "en": "Home"},
    {"key": "money", "emoji": "💳", "he": "כסף", "en": "Money"},
    {"key": "work", "emoji": "💼", "he": "עבודה", "en": "Work"},
    {"key": "personal", "emoji": "👤", "he": "אישי", "en": "Personal"},
    {"key": "general", "emoji": "📌", "he": "כללי", "en": "General"},
]


def localised_presets(lang: str = "he") -> list[dict]:
    """Flatten the bilingual preset table for one language."""
    out = []
    for p in PRESETS:
        out.append(
            {
                "key": p["key"],
                "emoji": p["emoji"],
                "category": p["category"],
                "name": p["name"].get(lang, p["name"]["en"]),
                "description": (p.get("description") or {}).get(lang, ""),
                "priority": p.get("priority", "normal"),
                "intensity": p.get("intensity", "relentless"),
                "repeat_kind": p.get("repeat_kind", "none"),
                "repeat_interval": p.get("repeat_interval", 1),
                "anchor_to_completion": p.get("anchor_to_completion", False),
                "require_confirmation": p.get("require_confirmation", False),
                "stages": [
                    {
                        "offset_minutes": s["offset_minutes"],
                        "kind": s["kind"],
                        "label": s["label"].get(lang, s["label"].get("en", "")),
                    }
                    for s in p["stages"]
                ],
            }
        )
    return out


def get_preset(key: str) -> dict | None:
    for p in PRESETS:
        if p["key"] == key:
            return p
    return None
