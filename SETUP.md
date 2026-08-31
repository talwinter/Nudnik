# Setup checklist

Follow top to bottom. Every section is labelled with its cost **before** you
start it.

Everything marked **💚 FREE** costs nothing, ever — no trial, no card, no
account with a paid tier waiting behind it. The only two paid things in this
project are at the very bottom under **skip these for now**.

You can stop after **Step 5** and have a fully working app.

---

## Step 0 · What you need first

### 💚 FREE

- Docker Desktop running on your PC
- Your Cloudflare tunnel + domain (you already have this)
- An Android phone

Nothing to install beyond Docker. No Python, no Node — it all runs in the
container.

---

## Step 1 · Pick your public address

### 💚 FREE

Decide the hostname now, because it gets baked into notification links.

Something like `nudnik.yourdomain.com`.

In the **Cloudflare Zero Trust dashboard** → Networks → Tunnels → your tunnel →
**Public Hostname** → Add:

| Field | Value |
|---|---|
| Subdomain | `nudnik` |
| Domain | `yourdomain.com` |
| Service type | `HTTP` |
| URL | `nudnik-app:8000` — if cloudflared runs as a container (see below) |
| URL | `localhost:8080` — if cloudflared runs on the host, with the localports override |

Cloudflare provides the HTTPS certificate automatically. You do **not** need
Caddy while using a tunnel.

### Running several apps on one server

By default this stack publishes **no ports at all**. Containers are reached by
name from the tunnel connector, which means every app on the server can use its
natural internal port and none of them can collide.

```bash
docker network create edge      # once per server
docker compose -f deploy/docker-compose.cloudflared.yml up -d
docker compose up -d
```

Any other app joins the same pattern: add `networks: [edge]`, delete its
`ports:` block, and point its hostname at `http://its-container-name:PORT`.

> **If a cloudflared already runs on your host, do not reuse its token here.**
> Cloudflare treats two connectors on one tunnel as HA replicas and
> load-balances between them, so half your requests would reach the connector
> that cannot see the app. Create a *second* tunnel for the container instead —
> a hostname belongs to exactly one tunnel, so both coexist and you can migrate
> hostnames one at a time with no downtime.

> **Why this matters:** Web Push, the installed app, and every Done/Snooze link
> are bound to this exact origin. Changing it later breaks all three.

---

## Step 2 · Configure and start

### 💚 FREE

In `H:\Projects\OpenCode`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Change **exactly three lines**, leave everything else blank:

```ini
PUBLIC_URL=https://nudnik.yourdomain.com
POSTGRES_PASSWORD=pick-something-long
ADMIN_PASSWORD=pick-something-else
```

> **ADMIN_PASSWORD is not optional once a tunnel is pointing at this.** Blank
> means no authentication at all — anyone who reaches the address can read and
> change your reminders, medical details included, and retrieve your API key.
>
> Setting it does **not** break notifications: the Done/Snooze links in a
> notification and the calendar feed carry their own tokens and keep working on
> a device that has never signed in. You sign in once per browser and the
> session lasts 90 days.

> Leave every channel value blank. A placeholder like `your-email@gmail.com`
> seeds a broken channel that then fails silently.

Then:

```powershell
docker compose up -d
docker compose logs -f app
```

Wait for `Nudnik is up`, then Ctrl+C (that only stops the log view, not the app).

Check it locally first: <http://localhost:8080>

Then check the tunnel: `https://nudnik.yourdomain.com`

**If `PUBLIC_URL` was wrong:** it only seeds the database on first run. Fix it
in the app under **Settings → Public address**, not in `.env`.

---

## Step 3 · Install on your phone

### 💚 FREE

On the Android phone, in **Chrome** (not Samsung Internet, not Firefox):

1. Go to `https://nudnik.yourdomain.com`
2. Menu **⋮ → Add to Home screen** → Install
3. **Close Chrome. Open the app from the home-screen icon.**

Step 3 is not optional. Notifications only arrive with the browser closed if
you opened the *installed* app.

---

## Step 4 · Turn on notifications

### 💚 FREE

**You do not install anything for this step.** No ntfy, no Pushover, no
Telegram. Pushover is not part of this project at all — ntfy replaced it.

**Push *is* a channel.** "Browser notifications" (התראות דפדפן) is the first
channel in the escalation ladder, it is on by default, and it starts working
the moment this device subscribes. ntfy, Telegram and email are all *extra*
channels layered on top later.

In the installed app:

1. **הגדרות / Settings** (⚙ in the bottom bar)
2. The **first** section is **הפעל התראות במכשיר הזה** — tap the purple button
3. Accept the Android permission prompt
4. Confirm **מכשירים רשומים / Registered devices** shows `1`
5. Tap **בדיקה / Test** in that same section's header (top-left of the section)

You should get a notification with **בוצע** and **דחה** buttons on it.

There is also a **ערוצים / Channels** page in the side menu listing every
channel with its own Test button and a live ready/not-configured badge. Right
now only *התראות דפדפן* will show as ready — that is correct and enough.

**If nothing arrives:**

| Symptom | Fix |
|---|---|
| Button does nothing | You are in Chrome, not the installed app. Open it from the home-screen icon |
| "הדפדפן חוסם התראות" | Chrome → site settings → Notifications → Allow |
| Devices stays `0` | Public address is not HTTPS, or does not match the URL you opened |
| Test says "no devices subscribed" | Step 2 did not complete — redo it inside the installed app |
| UI looks like an older version | **Settings → נתונים → אלץ עדכון גרסה**. See "Updates" below |
| Test succeeds but the notification lands on your **desktop** instead | This phone is not subscribed. Push goes to *every* registered device, so a "success" can mean another machine got it. Check the device list under Settings → the subscribed ones are listed and **this device is marked ★** |

> **Notification arrives in the drawer but does not pop up?** That is Android's
> notification *importance*, not the app. The push worked. Turn on floating /
> pop-up notifications for the app:
>
> First, make sure you are on a build from **after the notification-tag fix**
> (see the note below) — a repeated tag used to be treated by Android as a
> silent in-place update, which produced exactly this symptom and had nothing
> to do with your phone.
>
> If it persists, set the notification importance:
>
> - **Stock Android / Nothing OS / Pixel:** Settings → Notifications →
>   App notifications → נודניק → set the category to **Default** or **High**
> - **Samsung (One UI):** Settings → Notifications → App notifications →
>   נודניק → enable **Pop-up style**
> - **Xiaomi / Redmi / POCO (MIUI, HyperOS):** Settings → Apps → Manage apps →
>   נודניק → Notifications → enable **Floating notifications**, **Lock screen**
>   and **Sound**. MIUI defaults these off
>
> **Testing repeatedly? Only the first will float.** Android throttles heads-up
> banners when one app posts several times in quick succession — the rest go
> straight to the status bar. Leave ~2 minutes between tests. Real escalation
> rungs are 10 min to 4 h apart, so they never hit this.
>
> **A floating banner is still not guaranteed.** Heads-up notifications share a
> single contended surface: if another app posts one immediately afterwards it
> preempts yours, and the reminder drops to the drawer. No notification-based
> app can prevent that — only a full-screen alarm activity can, which is why the
> companion app is on the roadmap.
>
> If you want alerts that reliably interrupt you, this is the point where
> **ntfy (Step 6)** earns its place — its Android app exposes real priority
> levels instead of leaving it to the browser's default channel.

> **Each device subscribes separately.** Enabling notifications on your PC does
> nothing for your phone, and vice versa. Repeat Step 4 on every device you want
> notified. The device list in Settings shows exactly which ones are registered.

---

## Step 4b · Install on your desktop too

### 💚 FREE

Worth doing, and arguably the **stronger** platform of the two.

Chrome on Windows honours `requireInteraction`, which Android ignores — so a
desktop notification **stays on screen until you act on it**. It cannot be
swiped past or covered by the next app's banner. If you are at the PC when a
reminder fires, it will genuinely interrupt you.

1. Open `https://nudnik.yourdomain.com` in Chrome on the PC
2. Address bar → install icon (⊕), or **⋮ → Cast, save and share → Install**
3. Open the installed app → Settings → **הפעל התראות במכשיר הזה** → Test

You also get an **ambient count**: the number of overdue loops is painted on
the taskbar icon and in the window title. Unlike a notification, that cannot be
missed, throttled, or covered — it just sits there while something is open.

> **One gotcha:** for push to arrive while the app window is closed, Chrome must
> still be running in the background. Chrome → Settings → System → **Continue
> running background apps when Google Chrome is closed**. Windows Focus Assist
> / Do Not Disturb will also hold notifications.

Each device subscribes separately, so doing this does not affect your phone.

---

## Step 5 · Create your medicine reminder

### 💚 FREE

This is the whole point, so do it by hand once to see the machinery.

**+ הוספה** → **פרטים…** (the full editor), then:

| Field | Value |
|---|---|
| מה צריך לעשות | `לקחת את התרופה` |
| מתי האירוע עצמו | 9 September, 09:00 |
| קטגוריה | בריאות |
| כמה חזק לנדנד | **נודניק** |
| חזרתיות | חודשי, כל **2** |
| ספור מרגע הביצוע | **on** ← important |
| טלפון לביצוע | the clinic's number |

Then under **שלבים** add three stages:

| Days | Label |
|---|---|
| `-14` | `להתקשר למרפאה ולהזמין את התרופה` |
| `-3` | `לוודא שהתרופה הגיעה` |
| `0` | `לקחת את התרופה` |

Save.

**What should happen immediately:** because 14 days before 9 September has
already passed, the "call the clinic" stage appears **right now** under
**באיחור** and starts nagging. That is the behaviour that fixes your actual
problem.

> **ספור מרגע הביצוע** is why this beats a calendar: take the pill four days
> late and the next dose is scheduled two months from *when you took it*, with
> the pharmacy call re-chained 14 days ahead of that.

**You are done. Everything below is optional.**

---

## Step 6 · ntfy — push with zero Google

### 💚 FREE

Already running in your stack. Worth doing because it is fully self-hosted and
does not route through Google's push relay at all.

**6a.** Add a second tunnel hostname, same as Step 1:

| Field | Value |
|---|---|
| Subdomain | `ntfy` |
| URL | `localhost:8081` |

**6b.** Add to `.env` and restart:

```ini
NTFY_PUBLIC_URL=https://ntfy.yourdomain.com
```

```powershell
docker compose up -d
```

**6c.** Create a user (the server denies everything by default) and a token:

```powershell
docker compose exec ntfy ntfy user add --role=admin nudnik
docker compose exec ntfy ntfy token add nudnik
```

The first prompts for a password — remember it. The second prints a token
starting `tk_`.

**6d.** In the app: **Settings → ntfy**
- Enable
- URL: leave as `http://ntfy:80` (internal Docker address — correct as-is)
- Token: paste the `tk_…`
- Copy the **Topic**
- **Test**

**6e.** On the phone: install **ntfy** from Play Store → ⋮ → *Manage users* →
add `https://ntfy.yourdomain.com` with your username/password → subscribe to
that topic.

> Do not share the topic name — it is the only thing protecting it. Priority is
> capped at 4, so your phone's Do Not Disturb still wins.

---

## Step 7 · Telegram — including adding reminders by text

### 💚 FREE

Telegram bots are free with no limits.

**7a.** Open [@BotFather](https://t.me/botfather) → `/newbot` → follow prompts →
copy the token.

**7b.** App: **Settings → טלגרם** → paste token → enable.

**7c.** Get your API key from **Settings → חיבורים → מפתח API** (click פרטים to
reveal), then run:

```powershell
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://nudnik.yourdomain.com/hooks/telegram/<API_KEY>"
```

**7d.** Send `/start` to your bot. It saves your chat id automatically.

**7e.** **Test.**

Now you can text the bot to create reminders:

```
לשלם ארנונה בעוד שבועיים
טסט לרכב ב-15.3
```

---

## Step 8 · Email

### 💚 FREE

Free with a Gmail account you already have.

**Settings → אימייל:**

| Field | Value |
|---|---|
| SMTP host | `smtp.gmail.com` |
| Port | `587` |
| User | your Gmail address |
| Password | **App Password**, not your real password |
| Send to | your Gmail address |

To get an App Password: Google Account → Security → **2-Step Verification must
be on** → App passwords → generate. Your normal password will be rejected.

**Test.** The email arrives with working Done / Snooze buttons.

---

## Step 9 · Calendar feed

### 💚 FREE

**Settings → חיבורים → הזנת יומן** → copy the URL.

Google Calendar → Other calendars → **+** → *From URL* → paste.

Read-only on purpose — the calendar shows what is coming, the app stays the
only place a loop can be closed.

---

## Step 10 · Webhook (only if you use Discord / Slack / Home Assistant)

### 💚 FREE

**Settings → Webhook** → paste any webhook URL → enable → Test.

Discord and Slack webhook URLs work with no configuration — the payload already
carries both `content` and `text`.

### Sending any other API's shape

Fill in **Body template** and the webhook sends exactly that JSON instead of the
default. Placeholders: `{{title}}`, `{{body}}`, `{{text}}`, `{{done_url}}`,
`{{snooze_url}}`, `{{open_url}}`, `{{phone}}`, `{{attempts}}`,
`{{occurrence_id}}`.

Example — a WhatsApp gateway such as GreenAPI or a self-hosted WAHA:

```
URL       https://api.green-api.com/waInstance<ID>/sendMessage/<TOKEN>
Template  {"chatId":"972501234567@c.us","message":"{{title}}
{{body}}

✅ {{done_url}}"}
```

Values are JSON-escaped on substitution, so quotes or newlines in a reminder
title cannot break the payload. A malformed template fails loudly with the
parse error rather than silently sending nothing.

---

## Skip these for now

### 💰 COSTS MONEY

**SMS and WhatsApp** — needs a Twilio account. Israeli SMS is billed per
message. These sit at tier 4, so they only fire after seven other channels have
already tried. Leave them off.

**Call assist** (have it phone the clinic and connect you) — needs a phone
number (~$3–5.50/month) plus ~$1 per call. At six calls a year that is ~$70/year
for something the free 📞 button in every notification mostly already solves.
Revisit only if hold queues turn out to be the real blocker.

**Oracle VPS** — the Always Free tier genuinely costs nothing, but there is no
reason to move off your PC until the app has proved itself. When you do:
`docker compose up -d` on the box, repoint the tunnel, change Public address.
Nothing else changes.

---

## Daily use

- **עכשיו** — what is chasing you right now
- Tap **✓ בוצע** on the notification itself; you never need to open the app
- Swiping a notification away does **nothing** — it comes back
- **תובנות** after a few weeks tells you which reminders are not working and why

---

## Deploying a code change

The image bakes `app/` in, so after any code change:

```powershell
docker compose up -d --build
```

**Your data survives this.** Postgres lives in a named volume, so reminders,
settings, the VAPID keypair, your API key and phone push subscriptions all
persist. Only the app image is replaced.

Then reopen the app on your phone — it updates itself (see below).

### Dev mode: edit without rebuilding

Rebuilding for a one-line CSS tweak gets old fast. This mounts the source into
the container instead:

```powershell
docker compose -f docker-compose.yml -f deploy/docker-compose.dev.yml up -d
```

- **HTML / CSS / JS** — just reload the page
- **Python** — uvicorn restarts itself
- Ticks every 10s instead of 30s so escalations are quicker to watch

Use plain `docker compose up -d` for the real thing; a bind mount makes the
running code depend on whatever is on the host disk, which is the opposite of
what you want in production.

---

## Updates — and why you will not get a stale version

The usual PWA complaint is that the app keeps running old code because a
service worker is serving its own cached copy. This one is built not to do
that:

- Every front-end file contributes to a **build fingerprint**
- That fingerprint is stamped into the asset URLs *and* into `sw.js` itself
- Different bytes for `sw.js` means the browser installs a new worker, which
  claims the page, and the app **reloads itself once**
- It also re-checks whenever you bring the app back to the foreground

You can see the running build in the **bottom-left of the sidebar** (`build
a1b2c3d4e5`). After a `docker compose up -d` with new code, reopen the app and
that string should change on its own.

If it ever does not: **Settings → נתונים → אלץ עדכון גרסה**. That clears only
this app's cached shell and reloads. **Your reminders, settings and
notification subscription are not touched** — reminders live in Postgres on the
server, not in the browser.

You should never need to open Chrome's own site settings.

---

## If something breaks

```powershell
docker compose logs -f app        # what the app is doing
docker compose restart app        # most things
docker compose down; docker compose up -d
```

**Settings → נתונים → הרץ את המנוע עכשיו** forces an escalation tick immediately
instead of waiting.

Every delivery attempt is recorded per reminder — open any item → **יומן
שליחות**. If a notification did not arrive, the reason is written there.
