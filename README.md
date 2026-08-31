# נודניק · Nudnik

**לא מרפה עד שסגרת** — *it does not let go until you close it.*

A self-hosted reminder PWA built around one idea: every other reminder app
treats *"notification delivered"* as success. Nudnik treats **"you marked it
done"** as the only success. Everything else is an **open loop** that keeps
escalating — through more channels, more often — until a human closes it.

Hebrew-first with full RTL, English included. Installs to an Android home
screen and delivers real push notifications with **Done / Snooze / Call**
buttons inside the notification itself.

---

## Why this exists

The failure mode this app is built to kill:

> I put the medicine on the calendar, and a reminder 14 days before to order it.
> Then I dismissed the reminder without doing anything, and forgot again.

Three things cause that, and each has a direct countermeasure:

| The failure | What Nudnik does |
|---|---|
| A dismissed notification is gone forever | Dismissing does **nothing**. Only *Done* or *Snooze* closes a loop |
| The reminder fires when you can't act | **Stage chains** — the errand two weeks earlier is its own reminder |
| One channel, one chance | **Escalation ladder** — quiet at first, every channel you own by the end |
| Acting requires opening the app | **Done, Snooze and Call live inside the notification** |
| You can't tell if it's even working | **Insights** measures itself and tells you what to change |

---

## The model

```
Reminder  ──▶  Occurrence  ──▶  NotificationLog
(the plan)     (one open loop)   (every delivery attempt)
```

A **Reminder** is a definition. An **Occurrence** is one concrete thing that
must be acknowledged. Delivery is *only* ever recorded in the log — it never
closes anything.

### Stage chains

The hard part of a recurring obligation is rarely the event. It is the errand
that makes the event possible. One reminder produces a chain:

```
−14 days  להתקשר למרפאה ולהזמין את התרופה     ← the part that actually gets forgotten
 −3 days  לוודא שהתרופה הגיעה
      0   לקחת את התרופה
```

Add that reminder today for a dose ten days out and the −14 day stage is
already overdue — so it nags **immediately** rather than being silently
dropped.

### Completion-anchored recurrence

"Every 2 months" of a medicine you took four days late should be two months
from **when you took it**, not from the plan. Turn on *count from when I
finish* and the next cycle is measured from `done_at`.

### The escalation ladder

`relentless` profile — the default:

| Attempt | After due | Tier | Channels |
|---:|---:|---:|---|
| 1 | 0 min | 0 | push |
| 2 | 10 min | 0 | push |
| 3 | 30 min | 1 | push, ntfy |
| 5 | 2 h | 2 | + gotify, telegram, matrix |
| 7 | 8 h | 3 | + email, webhook |
| 9 | 18 h | 4 | + sms, whatsapp |
| … | every 4 h | 4 | everything, forever |

`gentle` stops after three tries. `normal` widens over a day then knocks daily.

Snoozing three times stops resetting the ladder — "later, later, later" no
longer buys you the quietest channel forever.

---

## What's in the box

**Reminding**
- Multi-stage chains with prep / main / follow-up stages
- Recurrence: daily, weekly (by weekday), monthly, yearly, every *N*, or anchored to completion
- Per-reminder intensity, priority, channel pinning
- Quiet hours (held, not dropped) — `critical` priority overrides
- Snooze presets incl. *this evening*, *tomorrow morning*, *the weekend*
- Daily brief and weekly look-ahead — catches whatever you dismissed
- Accountability contact: after *N* ignored reminders, someone else gets told
- Phone number per reminder → a **call button inside the notification**

**Channels** — every one carries Done / Snooze / Call
- **Web Push** (Android PWA, self-generated VAPID — no Firebase project)
- **ntfy** — self-hosted, your own server, zero Google
- **Gotify** — self-hosted alternative
- **Telegram** — inline buttons, *and* an inbound bot to add reminders by texting
- **Matrix** — any homeserver
- **Email** — SMTP, HTML with action buttons
- **Webhook** — Discord, Slack, Home Assistant, n8n (body carries both `content` and `text`)
- **SMS / WhatsApp** — via Twilio
- **Call assist** — provider-agnostic hook: dial, wait on hold, ring you when a human answers

**Admin console** (identical on phone and desktop)
- **עכשיו / Now** — what is chasing you right now
- **לוח זמנים / Timeline** — what is coming, and when
- **תזכורות / Reminders** — full table; restacks into cards on mobile
- **תובנות / Insights** — is this actually working
- **ערוצים / Channels** — live status, one-tap test per channel
- **יומן פעילות / Activity** — audit trail
- **Delivery log per occurrence** — *"why didn't I get notified?"* has an answer

**Input**
- Hebrew + English natural language quick-add, rule-based, no model or API key
  - `לקחת תרופה ב-9 בספטמבר כל חודשיים` → title, date, every-2-months
  - Handles Hebrew duals: `יומיים`, `שבועיים`, `חודשיים`
- 10 templates with prep chains pre-built (medicine refill, טסט, warranty, passport, bills…)
- REST API with key auth · ICS calendar feed · JSON import/export

---

## Quick start

### Local development

```bash
pip install -r requirements.txt
python scripts/fetch_fonts.py          # vendor fonts locally (once, needs internet)
python scripts/gen_icons.py            # generate PWA icons
uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000>. A VAPID keypair, API key and calendar token are
generated on first run and stored in the database.

Want it populated to look at? `python scripts/seed_demo.py`

### Docker (the real deployment)

```bash
cp .env.example .env      # set PUBLIC_URL and POSTGRES_PASSWORD
docker compose up -d
```

Brings up **app + Postgres + ntfy**. Nothing calls a third-party service.

On a VPS with a public IP, add Caddy for automatic HTTPS:

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.caddy.yml up -d
```

Behind a Cloudflare tunnel you don't need Caddy — the tunnel terminates TLS.

Everything is arm64-compatible, so it runs unchanged on an Oracle Ampere box.

---

## Getting notifications on Android

Web Push **requires HTTPS**. `localhost` works for development; a phone does
not. Use a named Cloudflare tunnel on your own domain, or Caddy.

1. Set **Public address** in Settings to your real HTTPS origin.
   This is what the Done/Snooze buttons in email and Telegram point at.
2. Open the site on the phone → **Install as an app** (Chrome ⋮ → *Add to Home screen*).
   Installing is required for notifications to arrive with the browser closed.
3. Open the installed app → Settings → **Enable notifications on this device**.
4. Settings → Channels → **Test** to confirm.

> Use a **named** tunnel, not a quick tunnel. Quick tunnels get a new URL every
> restart, and push subscriptions, the installed app, and every action link are
> all bound to the origin — they all break when it changes.

### About Web Push and "your own Firebase"

Web Push is a **W3C standard**, not a Google product. Nudnik signs with a VAPID
keypair it generates itself and encrypts payloads with keys the browser
provides. There is no Firebase project, no SDK, no `google-services.json`.

The one piece nobody can self-host is the *push endpoint* for a given browser —
Chrome's lives on FCM, Firefox's on Mozilla. The browser vendor chooses it; the
spec gives the app no say. That endpoint is an OS-level socket, which is the
only reason a notification can wake a sleeping phone with the app closed.

**The relay cannot read your reminders** — payloads are end-to-end encrypted, so
it sees an opaque endpoint id, ciphertext and a timestamp.

If you want *zero* Google involvement, that is what **ntfy** is for: install the
ntfy Android app, point it at your own server, and tier 1+ escalation never
touches Google at all.

### Do Not Disturb

Respected. ntfy priority is capped at 4 by default, because DND is you deciding
you are unavailable. Only a reminder explicitly marked **critical** uses
priority 5, which overrides it.

---

## Configuration

Environment variables in `.env` only **seed** the database on first run. After
that the admin UI owns them, so channels can be rewired without a redeploy.
Leave a value blank rather than filling in a placeholder — a placeholder seeds a
broken channel that then fails silently.

Secrets are masked in the settings API. Values meant to be copied (API key,
calendar token, ntfy topic) are available through an explicit reveal endpoint.

---

## Setting up each channel

Every channel has a **Test** button in Settings and on the Channels page. Use
it — it sends a real message through the real code path and reports the actual
error string if something is wrong. A channel that is enabled but misconfigured
shows as *not configured* rather than pretending to work.

You do not need all of these. **Push alone is enough to start**; each extra
channel just widens the escalation ladder.

| Channel | Cost | Needs | Tier it joins |
|---|---|---|---|
| Push | free | HTTPS + installed PWA | 0 |
| ntfy | free | self-hosted (in the compose file) | 1 |
| Gotify | free | self-hosted | 2 |
| Telegram | free | a bot token | 2 |
| Matrix | free | a homeserver account | 2 |
| Email | free | your own SMTP | 3 |
| Webhook | free | any URL | 3 |
| SMS / WhatsApp | **paid** | a Twilio account | 4 |

### Push — start here

Nothing to configure. A VAPID keypair is generated on first run.

1. Serve the app over **real HTTPS** (your tunnel). `localhost` works on a
   desktop but never on a phone.
2. Settings → **Public address** must be that HTTPS origin.
3. On Android: open the site → Chrome **⋮ → Add to Home screen**. Installing is
   required for delivery while the browser is closed.
4. Open the *installed* app → Settings → **Enable notifications on this device**
   → accept the browser prompt.
5. Hit **Test**.

If the button does nothing, check Settings shows the device count above zero.
Permission denied once is sticky — clear it in Chrome → site settings.

### ntfy — self-hosted push, no Google

Already running if you used `docker compose`. It is off by default because it
needs a public hostname your phone can reach.

1. Tunnel `ntfy.yourdomain.com` → `http://localhost:8081`, and set
   `NTFY_PUBLIC_URL=https://ntfy.yourdomain.com` in `.env`.
2. Create a publishing user (the container denies everything by default):
   ```bash
   docker compose exec ntfy ntfy user add --role=admin nudnik
   docker compose exec ntfy ntfy access nudnik "*" rw
   ```
3. Settings → ntfy → enable. Leave the URL as `http://ntfy:80` (that is the
   internal Docker address Nudnik publishes to). Copy the **topic**.
4. Install the ntfy app on Android, add your server
   `https://ntfy.yourdomain.com`, subscribe to that topic.
5. Test.

The topic name is the only secret protecting it, so do not share it. Priority
is capped at 4 so Do Not Disturb still wins.

### Telegram — and adding reminders by text

1. Create a bot with [@BotFather](https://t.me/botfather), paste the token into
   Settings → Telegram, enable it.
2. Register the webhook (the path secret is your API key, from
   Settings → Integrations):
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your.domain/hooks/telegram/<API_KEY>"
   ```
3. Send `/start` to your bot — it learns and saves your chat id by itself, so
   you never have to look it up.
4. Test.

From then on, texting the bot creates a reminder:
`לשלם ארנונה בעוד שבועיים`

Skip step 2 if you only want outgoing notifications; the chat id can also be
pasted in by hand.

### Email

Any SMTP server. Settings → Email:

| Field | Gmail | Generic |
|---|---|---|
| Host | `smtp.gmail.com` | your server |
| Port | `587` | `587` (STARTTLS) or `465` (SSL) |
| User | your address | your address |
| Password | **App Password** | your password |
| Send to | where reminders go | — |

Gmail needs an **App Password** (Google Account → Security → 2-Step
Verification → App passwords). Your normal password will be rejected.

Port `465` switches to implicit SSL automatically; anything else uses STARTTLS.

Emails arrive with real **Done / Snooze / Open** buttons, so you can close a
loop straight from your inbox.

### Webhook — Discord, Slack, Home Assistant, n8n

Settings → Webhook → paste any URL. The body carries `content` *and* `text`, so
a raw Discord or Slack webhook URL works with no mapping at all:

```json
{
  "title": "…", "body": "…", "occurrence_id": 42, "tier": 3,
  "attempts": 7, "links": { "done": "https://…" },
  "content": "**title**\nbody",
  "text": "*title*\nbody"
}
```

For Home Assistant, point it at a webhook trigger and use `links.done` to build
whatever automation you like.

### Gotify

Self-host the container, create an application, copy its token into
Settings → Gotify along with the server URL. Alternative to ntfy — you do not
need both.

### Matrix

Settings → Matrix needs three values: homeserver URL
(`https://matrix.org` or your own Synapse), an access token, and the room id
(`!abc123:server`). Get an access token from Element under
Settings → Help & About → Access Token.

### SMS and WhatsApp — the only paid channels

Both go through [Twilio](https://twilio.com) and sit at tier 4, so they only
fire on a reminder you have been ignoring for many hours.

1. Create a Twilio account, copy the **Account SID** and **Auth Token**.
2. **SMS**: buy a number, put it in *From*, your mobile in *To*.
3. **WhatsApp**: join the Twilio WhatsApp sandbox, then use
   `whatsapp:+1415...` as *From* and `whatsapp:+972...` as *To*.

Israeli SMS is billed per message. Leave these off unless the free channels
have genuinely failed you — the ladder already tries seven other things first.

### Calendar feed

Settings → Integrations → copy the ICS URL into Google or Apple Calendar.
Read-only on purpose: the calendar shows what is coming, the app stays the only
place a loop can be closed.

### Call assist

Point **Provider URL** at any voice service. Nudnik POSTs:

```json
{
  "occurrence_id": 42,
  "call_to": "03-6100000",
  "connect_to": "+9725...",
  "task": "להתקשר למרפאה ולהזמין את התרופה",
  "context": "מרשם 4471",
  "language": "he",
  "done_url": "https://your.domain/a/<token>"
}
```

Any 2xx is treated as accepted. The provider can close the loop itself by
hitting `done_url` when the call succeeds.

For Israeli lines, **DTMF sending matters more than Hebrew speech** — most
clinic IVRs are keypad-navigable, so "dial → wait → press 3 → detect human →
bridge" solves the common case with no transcription at all.

---

## Running it where it will not fall over

The engine tick is exposed as an HTTP endpoint as well as an internal job, so
the same code runs whether the host is always-on or sleeps:

```bash
curl -X POST "https://your.domain/api/tick?key=<API_KEY>"
```

Set `SCHEDULER_ENABLED=false` and drive it from an external cron if your host
sleeps. On an always-on box the internal scheduler handles it and the endpoint
is just a manual override.

Data lives in Postgres (or SQLite for development). Use a real volume — a
container filesystem does not survive a redeploy.

---

## Project layout

```
app/
  db.py            Reminder / Occurrence / NotificationLog models
  engine.py        the tick: promote, wake, escalate, retire
  escalation.py    ladder profiles and channel tiers
  recurrence.py    materialising occurrences, completion anchoring
  channels.py      every delivery channel
  digest.py        daily and weekly briefs
  analytics.py     does this actually work
  nlp.py           Hebrew/English quick-add parser
  api.py           REST surface
  main.py          app, action links, Telegram webhook, PWA plumbing
  static/          vanilla-JS PWA, no build step
deploy/            Caddy config and HTTPS compose override
scripts/           icons, fonts, seed data, tests
```

No build step, no node toolchain. The UI is vanilla JS served straight from
`app/static`.

---

## Tests

```bash
python scripts/test_flow.py    # the medicine scenario, end to end
python scripts/test_nlp.py     # quick-add parser regressions
```

`test_flow.py` walks the real thing: a three-stage medicine reminder whose prep
stage is already overdue, an ignored reminder chased over 24 simulated hours,
serial snoozing forcing escalation, completion anchoring producing the next
cycle 60 days out, and quiet hours holding a 2 a.m. nag until 07:30.

---

## Deliberate design decisions

- **Dismissing does nothing.** Only an explicit action closes a loop.
- **Delivery failure still climbs the ladder.** Higher tiers try *more*
  channels; one of them may be the one that works. Holding the ladder would
  leave a reminder with no working channel spinning silently at tier 0 forever.
- **Quiet hours hold, never drop.** A nag due at 2 a.m. fires at 07:30.
- **DND wins** unless the reminder is marked critical.
- **Static assets are `no-cache`.** Without it browsers apply heuristic caching
  and a service worker keeps serving last week's stylesheet after a deploy.
- **Numeric data is bidi-isolated.** `26.08, 21:48` is two digit runs joined by
  a neutral comma; inside RTL the comma flips them and the date renders after
  the time.
- **RTL via logical properties only.** Nothing is mirrored by hand, so flipping
  `dir` flips the whole interface with no per-rule overrides.
- **Every escalation rung is a new notification, not an update.** Reusing one
  tag per occurrence looks tidier, but Android treats a repeated tag as an
  in-place update: no banner, no sound. Ignore rung 1 and leave it in the
  drawer, and rungs 2..9 would silently overwrite it — the ladder would appear
  to escalate while actually going quiet. The tag carries the attempt number
  and the previous notification is closed explicitly instead.
- **The nag tally is real data.** Those tick marks are `attempts`, rendered.
  Seeing that a task has asked you nine times is itself the intervention.

---

## Roadmap

Things deliberately left out, with the reasoning:

- **A companion Android app.** Two things no notification-based app can fix,
  no matter the channel or priority:
  - a heads-up banner is a **single contended surface** — another app posting
    immediately afterwards preempts yours and your reminder silently drops to
    the drawer;
  - delivery depends on the server, the tunnel and the push relay all being up.

  A full-screen alarm activity fixes the first (an Activity cannot be replaced
  by another app's notification), and `AlarmManager.setAlarmClock()` fixes the
  second by holding the schedule on the phone, so it fires with no network at
  all. Everything server-side already exists — the app would sync open loops
  from the API, schedule local alarms, and post Done/Snooze back.

  Note that Android 14+ gates `USE_FULL_SCREEN_INTENT` behind a user grant for
  non-alarm apps, so verify it works on the target device before building.
- **Geofenced reminders** ("when I reach the pharmacy") — needs a native app.
- **Hebrew IVR navigation** — the call-assist hook is provider-agnostic and
  ready; the provider is the missing piece.

## License

MIT.
