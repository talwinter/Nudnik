/* Client-side dictionary.
 *
 * Kept in the browser so switching language is instant and works offline.
 * Hebrew first throughout -- it is the default, not the translation.
 */
(function (global) {
  'use strict';

  const DICT = {
    app_name: { he: 'נודניק', en: 'Nudnik' },
    tagline: { he: 'לא מרפה עד שסגרת', en: 'It does not let go until you close it' },

    /* navigation ------------------------------------------------------- */
    nav_now: { he: 'עכשיו', en: 'Now' },
    nav_timeline: { he: 'לוח זמנים', en: 'Timeline' },
    nav_reminders: { he: 'תזכורות', en: 'Reminders' },
    nav_insights: { he: 'תובנות', en: 'Insights' },
    nav_settings: { he: 'הגדרות', en: 'Settings' },
    nav_activity: { he: 'יומן פעילות', en: 'Activity' },
    nav_channels: { he: 'ערוצים', en: 'Channels' },

    nav_now_hint: { he: 'מה רודף אחריך עכשיו', en: 'What is chasing you right now' },
    nav_timeline_hint: { he: 'מה מתוכנן ומתי', en: 'What is coming, and when' },
    nav_reminders_hint: { he: 'ניהול כל התזכורות', en: 'Manage every reminder' },
    nav_insights_hint: { he: 'האם זה באמת עובד לך', en: 'Is this actually working' },

    /* actions ---------------------------------------------------------- */
    add: { he: 'הוספה', en: 'Add' },
    done: { he: 'בוצע', en: 'Done' },
    snooze: { he: 'דחה', en: 'Snooze' },
    skip: { he: 'דלג', en: 'Skip' },
    edit: { he: 'עריכה', en: 'Edit' },
    del: { he: 'מחיקה', en: 'Delete' },
    save: { he: 'שמירה', en: 'Save' },
    cancel: { he: 'ביטול', en: 'Cancel' },
    close_with_button: {
      he: 'סגור עם ✕ או שמור — כדי שלא תאבד מה שהזנת',
      en: 'Close with ✕ or Save — so you do not lose what you entered',
    },
    draft_restored: { he: 'שוחזרה טיוטה שלא נשמרה', en: 'Restored an unsaved draft' },
    close: { he: 'סגירה', en: 'Close' },
    reopen: { he: 'פתח מחדש', en: 'Reopen' },
    duplicate: { he: 'שכפול', en: 'Duplicate' },
    test: { he: 'בדיקה', en: 'Test' },
    copy: { he: 'העתק', en: 'Copy' },
    copied: { he: 'הועתק', en: 'Copied' },
    details: { he: 'פרטים', en: 'Details' },
    call: { he: 'חייג', en: 'Call' },
    nudge_now: { he: 'שלח עכשיו', en: 'Send now' },
    call_for_me: { he: 'תתקשר בשבילי', en: 'Call for me' },
    call_assist: { he: 'שיחה בשבילך', en: 'Call assist' },
    call_assist_hint: {
      he: 'נודניק יבקש מספק חיצוני לחייג, להמתין בתור ולחבר אותך רק כשעונה בן אדם. השיחה שדוחים היא בדרך כלל המשימה עצמה.',
      en: 'Nudnik asks an external provider to dial, wait in the queue, and ring you only once a human answers. The call you postpone is usually the task itself.',
    },
    call_assist_my_number: { he: 'המספר שלך', en: 'Your number' },
    call_placed: { he: 'הבקשה נשלחה — תקבל שיחה כשעונה בן אדם', en: 'Requested — you will be called when a human answers' },
    search: { he: 'חיפוש', en: 'Search' },
    all: { he: 'הכל', en: 'All' },

    /* now view --------------------------------------------------------- */
    overdue: { he: 'באיחור', en: 'Overdue' },
    due_today: { he: 'היום', en: 'Today' },
    upcoming: { he: 'בהמשך', en: 'Upcoming' },
    nothing_open: { he: 'הכל סגור', en: 'Everything is closed' },
    nothing_open_sub: {
      he: 'אין לולאות פתוחות. זה בדיוק המצב שאליו האפליקציה מנסה להביא אותך.',
      en: 'No open loops. This is exactly the state the app is trying to get you to.',
    },
    nothing_today: { he: 'שום דבר לא מתוכנן להיום', en: 'Nothing scheduled for today' },
    worst_offender: { he: 'הכי הרבה זמן פתוח', en: 'Open the longest' },
    asked_n: { he: 'ביקשתי {n} פעמים', en: 'Asked {n} times' },
    asked_1: { he: 'ביקשתי פעם אחת', en: 'Asked once' },
    open_for: { he: 'פתוח כבר {t}', en: 'Open for {t}' },
    due_in: { he: 'בעוד {t}', en: 'In {t}' },
    snoozed_to: { he: 'נדחה ל־{t}', en: 'Snoozed to {t}' },

    /* snooze options --------------------------------------------------- */
    snooze_10m: { he: '10 דקות', en: '10 minutes' },
    snooze_1h: { he: 'שעה', en: '1 hour' },
    snooze_3h: { he: '3 שעות', en: '3 hours' },
    snooze_evening: { he: 'הערב', en: 'This evening' },
    snooze_tomorrow: { he: 'מחר בבוקר', en: 'Tomorrow morning' },
    snooze_weekend: { he: 'סוף השבוע', en: 'The weekend' },
    snooze_next_week: { he: 'שבוע הבא', en: 'Next week' },
    snooze_title: { he: 'לדחות לאיזה מועד?', en: 'Postpone until when?' },
    snooze_warning: {
      he: 'דחייה חוזרת מעלה את רמת ההתראה אוטומטית.',
      en: 'Repeated snoozing raises the alert level automatically.',
    },

    /* editor ----------------------------------------------------------- */
    new_reminder: { he: 'תזכורת חדשה', en: 'New reminder' },
    edit_reminder: { he: 'עריכת תזכורת', en: 'Edit reminder' },
    quick_add: { he: 'הוספה מהירה', en: 'Quick add' },
    quick_add_ph: {
      he: 'לדוגמה: לקחת תרופה ב-9 בספטמבר כל חודשיים',
      en: 'e.g. take medicine on September 9 every 2 months',
    },
    quick_add_hint: {
      he: 'כתוב בשפה חופשית. אפשר גם לשלוח הודעה לבוט בטלגרם.',
      en: 'Write it however you like. You can also text the Telegram bot.',
    },
    pick_template: { he: 'בחר תבנית', en: 'Pick a template' },
    qa_when: { he: 'מתי האירוע', en: 'When is the event' },
    qa_when_hint: {
      he: 'אפשר להשאיר ריק אם כתבת תאריך בטקסט. תבנית עם שלבי הכנה חייבת תאריך — אחרת ההכנות יהיו באיחור כבר ברגע השמירה.',
      en: 'Leave blank if you wrote a date in the text. A template with prep stages needs one, or those stages are overdue the moment you save.',
    },
    template_hint: {
      he: 'תבנית מוסיפה אוטומטית את שלבי ההכנה — בדרך כלל הם החלק שנשכח.',
      en: 'A template adds the prep stages automatically — usually the part that gets forgotten.',
    },
    title_label: { he: 'מה צריך לעשות', en: 'What needs doing' },
    title_ph: { he: 'לקחת את התרופה', en: 'Take the medicine' },
    notes_label: { he: 'הערות', en: 'Notes' },
    notes_ph: { he: 'מספר מרשם, שם הרופא, כל דבר שיעזור לך לבצע', en: 'Prescription number, doctor name, anything that helps you act' },
    when_label: { he: 'מתי האירוע עצמו', en: 'When the event itself is' },
    when_hint: {
      he: 'שלבי ההכנה מחושבים ביחס למועד הזה.',
      en: 'Prep stages are calculated relative to this moment.',
    },
    category_label: { he: 'קטגוריה', en: 'Category' },
    priority_label: { he: 'דחיפות', en: 'Priority' },
    prio_low: { he: 'נמוכה', en: 'Low' },
    prio_normal: { he: 'רגילה', en: 'Normal' },
    prio_high: { he: 'גבוהה', en: 'High' },
    prio_critical: { he: 'קריטית', en: 'Critical' },
    prio_critical_hint: {
      he: 'קריטית מתעלמת משעות שקט ותצלצל גם ב-3 בלילה.',
      en: 'Critical ignores quiet hours and will ring at 3am.',
    },

    repeat_label: { he: 'חזרתיות', en: 'Repeat' },
    repeat_none: { he: 'פעם אחת', en: 'Once' },
    repeat_daily: { he: 'יומי', en: 'Daily' },
    repeat_weekly: { he: 'שבועי', en: 'Weekly' },
    repeat_monthly: { he: 'חודשי', en: 'Monthly' },
    repeat_yearly: { he: 'שנתי', en: 'Yearly' },
    every_n: { he: 'כל', en: 'Every' },
    unit_days: { he: 'ימים', en: 'days' },
    unit_weeks: { he: 'שבועות', en: 'weeks' },
    unit_months: { he: 'חודשים', en: 'months' },
    unit_years: { he: 'שנים', en: 'years' },
    repeat_hint_weeks: {
      he: 'שבועות = מספר ימים קבוע. "כל 8 שבועות" זה תמיד בדיוק 56 יום. "כל חודשיים" משתנה בין 59 ל-62 יום לפי אורך החודשים — לתרופות עדיף שבועות.',
      en: 'Weeks are a fixed number of days: "every 8 weeks" is always exactly 56. "Every 2 months" varies between 59 and 62 days depending on the months — for medication, prefer weeks.',
    },
    next_dates: { he: 'המועדים הבאים', en: 'Next dates' },
    anchor_completion: { he: 'ספור מרגע הביצוע', en: 'Count from when I finish' },
    anchor_completion_hint: {
      he: 'המחזור הבא ייספר מהיום שבו באמת ביצעת, לא מהתאריך המתוכנן. נכון לתרופות שנלקחות באיחור.',
      en: 'The next cycle counts from the day you actually did it, not the planned date. Correct for medicine taken late.',
    },

    stages_label: { he: 'שלבים', en: 'Stages' },
    stages_hint: {
      he: 'הוסף את הצעדים שצריכים לקרות לפני האירוע. זה מה שמונע את ה"שכחתי להזמין מראש".',
      en: 'Add the steps that must happen beforehand. This is what prevents "I forgot to order it in time".',
    },
    add_stage: { he: '+ שלב', en: '+ Stage' },
    stage_label_ph: { he: 'מה לעשות בשלב הזה', en: 'What to do at this stage' },
    days_before: { he: 'ימים לפני', en: 'days before' },
    dir_before: { he: 'ימים לפני האירוע', en: 'days before' },
    dir_after: { he: 'ימים אחרי האירוע', en: 'days after' },
    stage_inherit: { he: 'לפי התזכורת', en: 'As the reminder' },
    stage_time_hint: {
      he: 'שעה ריקה = לפי שעת האירוע. הגדר שעה לשלבים שתלויים בשעות פתיחה — אין טעם להזכיר לך להתקשר לבית מרקחת ב-19:00.',
      en: 'Blank time = the event’s time. Set one for stages that depend on opening hours — there is no point reminding you to phone a pharmacy at 19:00.',
    },
    stage_intensity_hint: {
      he: 'שלב שהוא רק "לשים לב" לא צריך לנדנד כל 4 שעות. בחר "עדין" לשלבים אינפורמטיביים — הם יתריעו כמה פעמים ואז יופיעו רק בסיכום היומי.',
      en: 'A stage that only tells you something does not need chasing every 4 hours. Pick "gentle" for informational stages — they alert a few times, then appear only in the daily brief.',
    },
    at_event: { he: 'ביום האירוע', en: 'on the day' },
    days_after: { he: 'ימים אחרי', en: 'days after' },

    intensity_label: { he: 'כמה חזק לנדנד', en: 'How hard to nag' },
    intensity_gentle: { he: 'עדין', en: 'Gentle' },
    intensity_normal: { he: 'רגיל', en: 'Normal' },
    intensity_relentless: { he: 'נודניק', en: 'Relentless' },
    intensity_gentle_hint: { he: 'כמה תזכורות ואז מרפה', en: 'A few reminders, then it lets go' },
    intensity_normal_hint: { he: 'מתרחב לערוצים נוספים, ואז דפיקה יומית', en: 'Widens channels, then a daily knock' },
    intensity_relentless_hint: {
      he: 'לא מפסיק. כל הערוצים, כל 4 שעות, עד שתסגור.',
      en: 'Never stops. Every channel, every 4 hours, until you close it.',
    },

    contact_label: { he: 'טלפון לביצוע', en: 'Phone to call' },
    contact_hint: {
      he: 'יופיע ככפתור חיוג בתוך ההתראה עצמה — מסיר את התירוץ "אין לי עכשיו את המספר".',
      en: 'Becomes a call button inside the notification — removes the "I do not have the number" excuse.',
    },
    link_label: { he: 'קישור', en: 'Link' },
    confirm_label: { he: 'לשאול אותי אם באמת עשיתי', en: 'Ask me whether I really did it' },
    buddy_label: { he: 'לערב איש קשר אם אני מתעלם', en: 'Involve my contact if I ignore it' },
    channels_label: { he: 'ערוצים', en: 'Channels' },
    channels_hint: {
      he: 'ריק = לפי הגדרות ברירת המחדל. ההסלמה תמיד מתרחבת לפי רמת הדחיפות.',
      en: 'Empty = follow the defaults. Escalation still widens by urgency.',
    },

    /* reminders table -------------------------------------------------- */
    col_reminder: { he: 'תזכורת', en: 'Reminder' },
    col_next: { he: 'הבא', en: 'Next' },
    col_repeat: { he: 'חזרתיות', en: 'Repeat' },
    col_intensity: { he: 'עצימות', en: 'Intensity' },
    col_open: { he: 'פתוח', en: 'Open' },
    col_actions: { he: 'פעולות', en: 'Actions' },
    no_reminders: { he: 'עדיין אין תזכורות', en: 'No reminders yet' },
    no_reminders_sub: {
      he: 'התחל מתבנית — היא כבר יודעת אילו שלבי הכנה צריך.',
      en: 'Start from a template — it already knows which prep stages you need.',
    },
    show_inactive: { he: 'הצג לא פעילות', en: 'Show inactive' },

    /* occurrence detail ------------------------------------------------ */
    the_chain: { he: 'שרשרת השלבים', en: 'The stage chain' },
    delivery_log: { he: 'יומן שליחות', en: 'Delivery log' },
    delivery_log_hint: {
      he: 'כל ניסיון שליחה נרשם כאן. אם לא קיבלת התראה — התשובה נמצאת כאן.',
      en: 'Every attempt is recorded here. If you did not get a notification, the answer is here.',
    },
    no_deliveries: { he: 'עדיין לא נשלחה אף התראה', en: 'No notifications sent yet' },
    cycle: { he: 'מחזור', en: 'Cycle' },
    cycle_current: { he: 'המחזור הנוכחי', en: 'Current cycle' },
    cycle_done_of: { he: '{done} מתוך {total} הושלמו', en: '{done} of {total} done' },
    cycle_all_done: { he: 'הושלם', en: 'Complete' },
    chain_hint: {
      he: 'כל מחזור חוזר על אותם שלבים. המחזור הקרוב פתוח, השאר מקופלים.',
      en: 'Every cycle repeats the same stages. The nearest one is open, the rest are collapsed.',
    },

    /* insights --------------------------------------------------------- */
    completion_rate: { he: 'אחוז השלמה', en: 'Completion rate' },
    avg_attempts: { he: 'תזכורות עד סגירה', en: 'Reminders per close' },
    first_try: { he: 'נסגר בפעם הראשונה', en: 'Closed on first nudge' },
    hours_late: { he: 'שעות איחור בממוצע', en: 'Avg hours late' },
    total_snoozes: { he: 'דחיות', en: 'Snoozes' },
    open_loops: { he: 'לולאות פתוחות', en: 'Open loops' },
    channel_perf: { he: 'איזה ערוץ באמת מזיז אותך', en: 'Which channel actually moves you' },
    channel_perf_hint: {
      he: 'הערוץ האחרון שנשלח לפני שסגרת מקבל את הקרדיט. אחרי כמה שבועות זה מראה על מה באמת שווה להסתמך.',
      en: 'The last channel sent before you closed gets the credit. After a few weeks this shows what is worth relying on.',
    },
    col_channel: { he: 'ערוץ', en: 'Channel' },
    col_sent: { he: 'נשלחו', en: 'Sent' },
    col_credited: { he: 'הובילו לסגירה', en: 'Led to close' },
    col_conversion: { he: 'יחס', en: 'Rate' },
    problems: { he: 'תזכורות שלא עובדות', en: 'Reminders that are not working' },
    problems_hint: {
      he: 'אלה התזכורות שדורשות הכי הרבה רדיפה. לרוב הבעיה היא בהגדרה, לא בך.',
      en: 'These need the most chasing. Usually the setup is wrong, not you.',
    },
    no_problems: {
      he: 'שום תזכורת לא דורשת רדיפה חריגה',
      en: 'No reminder needs unusual chasing',
    },
    fix_it: { he: 'תקן', en: 'Fix it' },
    activity_30d: { he: 'פעילות ב-30 יום', en: 'Activity over 30 days' },

    /* settings --------------------------------------------------------- */
    set_general: { he: 'כללי', en: 'General' },
    set_quiet: { he: 'שעות שקט', en: 'Quiet hours' },
    set_quiet_hint: {
      he: 'התראות שאמורות לצאת בשעות האלה יידחו לסוף החלון. דחיפות "קריטית" עוקפת אותן.',
      en: 'Notifications due in this window are held until it ends. Critical priority overrides it.',
    },
    set_brief: { he: 'סיכום יומי', en: 'Daily brief' },
    set_brief_hint: {
      he: 'רשימה אחת של כל מה שפתוח, בשעה קבועה. זה מה שתופס דברים שהתעלמת מהם.',
      en: 'One list of everything open, at a fixed time. This catches what you dismissed.',
    },
    set_channels: { he: 'ערוצי התראה', en: 'Notification channels' },
    set_integrations: { he: 'חיבורים', en: 'Integrations' },
    set_buddy: { he: 'איש קשר לאחריות', en: 'Accountability contact' },
    set_buddy_hint: {
      he: 'אחרי מספר תזכורות שהתעלמת מהן, האדם הזה יקבל הודעה. לחץ חברתי עובד כשכל השאר נכשל.',
      en: 'After enough ignored reminders, this person gets told. Social pressure works when nothing else does.',
    },
    set_danger: { he: 'נתונים', en: 'Data' },
    auth_off_title: { he: 'האפליקציה פתוחה לכל אחד', en: 'This instance has no password' },
    auth_off_body: {
      he: 'כל מי שמגיע לכתובת הזו יכול לראות ולשנות את התזכורות שלך, כולל פרטים רפואיים. הגדר ADMIN_PASSWORD בקובץ .env והפעל מחדש.',
      en: 'Anyone who reaches this address can read and change your reminders, medical details included. Set ADMIN_PASSWORD in .env and restart.',
    },
    auth_on: { he: 'מוגן בסיסמה', en: 'Password protected' },
    logout: { he: 'יציאה', en: 'Sign out' },
    lang_label: { he: 'שפה', en: 'Language' },
    tz_label: { he: 'אזור זמן', en: 'Timezone' },
    public_url_label: { he: 'כתובת ציבורית', en: 'Public address' },
    public_url_hint: {
      he: 'הכתובת שאליה מצביעים כפתורי "בוצע" בהתראות. חייבת להיות ה-HTTPS האמיתי שלך.',
      en: 'The address the Done buttons point at. Must be your real HTTPS origin.',
    },
    enable_push: { he: 'הפעל התראות במכשיר הזה', en: 'Enable notifications on this device' },
    push_is_a_channel: {
      he: 'התראות הדפדפן הן ערוץ בפני עצמו — לא צריך להתקין שום אפליקציה נוספת. זה הערוץ הראשון שנכנס לפעולה.',
      en: 'Browser notifications are a channel in their own right — nothing extra to install. This is the first channel the ladder uses.',
    },
    push_on: { he: 'התראות פעילות במכשיר הזה', en: 'Notifications are on for this device' },
    push_blocked: {
      he: 'הדפדפן חוסם התראות. יש לאשר בהגדרות האתר.',
      en: 'The browser is blocking notifications. Allow them in site settings.',
    },
    push_needs_https: {
      he: 'התראות דורשות HTTPS. פתח דרך הכתובת המאובטחת שלך.',
      en: 'Notifications require HTTPS. Open the secure address instead.',
    },
    install_app: { he: 'התקן כאפליקציה', en: 'Install as an app' },
    install_hint: {
      he: 'התקנה במסך הבית נדרשת כדי שהתראות יגיעו כשהדפדפן סגור.',
      en: 'Installing to the home screen is required for notifications to arrive with the browser closed.',
    },
    devices: { he: 'מכשירים רשומים', en: 'Registered devices' },
    calendar_feed: { he: 'הזנת יומן', en: 'Calendar feed' },
    calendar_feed_hint: {
      he: 'הדבק בגוגל קלנדר או ביומן של אפל כדי לראות את הכל שם. לקריאה בלבד — סגירה נעשית רק כאן.',
      en: 'Paste into Google or Apple Calendar to see everything there. Read-only — closing happens only here.',
    },
    api_key_label: { he: 'מפתח API', en: 'API key' },
    api_key_hint: {
      he: 'לחיבור מערכות אחרות, ולהפעלת המנוע מבחוץ אם השרת נרדם.',
      en: 'For wiring up other systems, and for driving the engine externally if the host sleeps.',
    },
    telegram_hook_hint: {
      he: 'רשום את הכתובת הזו כ-webhook של הבוט, ואז שלח /start לבוט. אחר כך אפשר להוסיף תזכורות פשוט בהודעה.',
      en: 'Register this as the bot webhook, then send /start to the bot. After that you can add reminders by texting it.',
    },
    export_data: { he: 'ייצוא גיבוי', en: 'Export backup' },
    import_data: { he: 'ייבוא גיבוי', en: 'Import backup' },
    send_brief_now: { he: 'שלח סיכום עכשיו', en: 'Send the brief now' },
    run_engine_now: { he: 'הרץ את המנוע עכשיו', en: 'Run the engine now' },
    force_refresh: { he: 'אלץ עדכון גרסה', en: 'Force update' },
    force_refresh_hint: {
      he: 'האפליקציה מתעדכנת לבד. הכפתור הזה הוא רק גלגל הצלה — הוא מוחק את הגרסה השמורה של האפליקציה בלבד וטוען מחדש. הנתונים, התזכורות וההרשמה להתראות לא נמחקים.',
      en: 'The app updates itself. This is only a lifeline — it clears the cached copy of the app and reloads. Your data, reminders and notification subscription are untouched.',
    },
    refreshing: { he: 'מרענן…', en: 'Refreshing…' },
    build_label: { he: 'גרסה', en: 'Build' },
    this_device: { he: 'המכשיר הזה', en: 'This device' },
    this_device_not_subscribed: {
      he: 'המכשיר הזה לא רשום להתראות. הבדיקה תגיע למכשירים אחרים בלבד — לחץ קודם על "הפעל התראות במכשיר הזה".',
      en: 'This device is not subscribed. A test would only reach your other devices — tap "Enable notifications on this device" first.',
    },
    sent_to_devices: { he: 'נשלח ל-{n} מכשירים', en: 'Sent to {n} device(s)' },
    no_devices: {
      he: 'אין מכשירים רשומים. אף התראה לא תגיע לשום מקום.',
      en: 'No devices registered. No notification can reach anywhere.',
    },
    remove_device: { he: 'הסר', en: 'Remove' },
    local_test: { he: 'בדיקה מקומית', en: 'Local test' },
    local_test_hint: {
      he: 'מציג התראה ישירות מהמכשיר, בלי לעבור דרך השרת. אם זה לא מופיע — הבעיה היא בהגדרות ההתראות של אנדרואיד או במצב "נא לא להפריע", ולא באפליקציה.',
      en: 'Shows a notification straight from this device, without going through the server. If this does not appear, the problem is Android notification settings or Do Not Disturb — not the app.',
    },
    diagnose: { he: 'אבחון', en: 'Diagnose' },
    local_test_sent: { he: 'נשלחה התראה מקומית', en: 'Local notification fired' },

    ch_push: { he: 'התראות דפדפן', en: 'Browser push' },
    ch_ntfy: { he: 'ntfy (עצמאי)', en: 'ntfy (self-hosted)' },
    ch_gotify: { he: 'Gotify (עצמאי)', en: 'Gotify (self-hosted)' },
    ch_telegram: { he: 'טלגרם', en: 'Telegram' },
    ch_matrix: { he: 'Matrix', en: 'Matrix' },
    ch_email: { he: 'אימייל', en: 'Email' },
    ch_webhook: { he: 'Webhook', en: 'Webhook' },
    ch_sms: { he: 'SMS', en: 'SMS' },
    ch_whatsapp: { he: 'וואטסאפ', en: 'WhatsApp' },
    ch_ready: { he: 'מוכן', en: 'Ready' },
    ch_not_ready: { he: 'לא מוגדר', en: 'Not configured' },
    tier_label: { he: 'נכנס לפעולה ברמה', en: 'Kicks in at level' },

    /* system ----------------------------------------------------------- */
    saved: { he: 'נשמר', en: 'Saved' },
    deleted: { he: 'נמחק', en: 'Deleted' },
    error: { he: 'משהו נכשל', en: 'Something failed' },
    confirm_delete: {
      he: 'למחוק את התזכורת וכל ההיסטוריה שלה?',
      en: 'Delete this reminder and all its history?',
    },
    offline: { he: 'אין חיבור — מוצג מידע שמור', en: 'Offline — showing saved data' },
    loading: { he: 'טוען…', en: 'Loading…' },
    never: { he: 'מעולם', en: 'Never' },
    now: { he: 'עכשיו', en: 'now' },
  };

  const RTL = ['he'];
  let lang = document.documentElement.lang === 'en' ? 'en' : 'he';

  function t(key, vars) {
    const entry = DICT[key];
    if (!entry) return key;
    let s = entry[lang] || entry.he || key;
    if (vars) {
      Object.keys(vars).forEach((k) => {
        s = s.replace(new RegExp('\\{' + k + '\\}', 'g'), vars[k]);
      });
    }
    return s;
  }

  function setLang(next) {
    lang = next === 'en' ? 'en' : 'he';
    document.documentElement.lang = lang;
    document.documentElement.dir = RTL.includes(lang) ? 'rtl' : 'ltr';
    try { localStorage.setItem('nudnik_lang', lang); } catch (e) { /* private mode */ }
  }

  function getLang() { return lang; }
  function isRTL() { return RTL.includes(lang); }
  function locale() { return lang === 'he' ? 'he-IL' : 'en-GB'; }

  /* Durations read naturally in both languages without a pluralisation
     library, because the units we use do not need one. */
  function humanDuration(minutes) {
    const m = Math.abs(Math.round(minutes));
    if (m < 1) return t('now');
    if (m < 60) return lang === 'he' ? `${m} דק׳` : `${m} min`;
    const h = Math.round(m / 60);
    if (m < 60 * 36) return lang === 'he' ? `${h} שע׳` : `${h}h`;
    const d = Math.round(m / 1440);
    if (m < 1440 * 14) return lang === 'he' ? `${d} ימים` : `${d}d`;
    const w = Math.round(m / (1440 * 7));
    if (m < 1440 * 60) return lang === 'he' ? `${w} שב׳` : `${w}w`;
    const mo = Math.round(m / (1440 * 30));
    return lang === 'he' ? `${mo} חוד׳` : `${mo}mo`;
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return d.toLocaleString(locale(), {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return d.toLocaleDateString(locale(), { day: 'numeric', month: 'long', year: 'numeric' });
  }

  function fmtDay(iso) {
    const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
    return d.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' });
  }

  function toDate(iso) {
    return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  }

  try {
    const saved = localStorage.getItem('nudnik_lang');
    if (saved) setLang(saved);
  } catch (e) { /* private mode */ }

  global.I18n = {
    t, setLang, getLang, isRTL, locale,
    humanDuration, fmtDateTime, fmtDate, fmtDay, toDate, DICT,
  };
})(window);
