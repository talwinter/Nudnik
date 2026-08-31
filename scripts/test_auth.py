"""The login gate.

Two things have to be true at once: an unauthenticated stranger must not be
able to read or change anything, and a notification's Done button must still
work on a device that has never logged in. Those pull in opposite directions,
so both are pinned here.

Run: python scripts/test_auth.py
"""
import os
import sys
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="nudnik-auth-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.environ["DATA_DIR"] + "/t.db"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ADMIN_PASSWORD"] = "s3cret-pass"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

failures = []


def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{extra}]" if extra else ""))
    if not cond:
        failures.append(label)


def main() -> int:
    with TestClient(app, follow_redirects=False) as anon:
        print("\n=== 1. A stranger is locked out ===")
        for path in ("/", "/#/settings"):
            r = anon.get(path)
            check(f"GET {path} shows the login page", r.status_code in (200, 401)
                  and "password" in r.text.lower(), str(r.status_code))

        for path in ("/api/reminders", "/api/settings", "/api/dashboard",
                     "/api/push/devices", "/api/events", "/api/logs"):
            r = anon.get(path)
            check(f"GET {path} refused", r.status_code == 401, str(r.status_code))

        r = anon.post("/api/reminders", json={"title": "x", "anchor_at": "2026-01-01T00:00:00Z"})
        check("POST /api/reminders refused", r.status_code == 401, str(r.status_code))

        r = anon.get("/api/settings/reveal?key=api_key")
        check("the API key cannot be revealed anonymously", r.status_code == 401,
              str(r.status_code))

        print("\n=== 2. Things that carry their own secret still work ===")
        for path in ("/api/health", "/api/version", "/sw.js", "/manifest.webmanifest",
                     "/static/css/app.css"):
            r = anon.get(path)
            check(f"{path} still reachable", r.status_code == 200, str(r.status_code))

        # An expired action token: the point is that the gate lets it through to
        # the handler, which then judges the token itself.
        r = anon.get("/a/not-a-real-token")
        check("action links reach their handler, not the login page",
              r.status_code == 200 and "password" not in r.text.lower(),
              str(r.status_code))

        r = anon.get("/api/calendar.ics?token=wrong")
        check("calendar feed judged by its own token, not the session",
              r.status_code == 403, str(r.status_code))

        r = anon.post("/api/tick?key=wrong")
        check("tick judged by the API key, not the session",
              r.status_code == 401, str(r.status_code))

        print("\n=== 3. Signing in ===")
        r = anon.post("/login", data={"password": "wrong", "next": "/"})
        check("wrong password rejected", r.status_code == 401, str(r.status_code))
        check("no cookie handed out on failure",
              "nudnik_session" not in r.cookies, str(dict(r.cookies)))

        r = anon.post("/login", data={"password": "s3cret-pass", "next": "/"})
        check("correct password accepted", r.status_code == 303, str(r.status_code))
        cookie = r.cookies.get("nudnik_session")
        check("session cookie issued", bool(cookie))
        check("cookie does not contain the password",
              bool(cookie) and "s3cret-pass" not in cookie)

    print("\n=== 4. A signed-in session can work ===")
    with TestClient(app, follow_redirects=False) as user:
        user.post("/login", data={"password": "s3cret-pass", "next": "/"})
        r = user.get("/api/reminders")
        check("reminders readable once signed in", r.status_code == 200, str(r.status_code))
        r = user.post("/api/reminders", json={
            "title": "בדיקה", "anchor_at": "2026-12-01T09:00:00Z"})
        check("reminders writable once signed in", r.status_code == 200, str(r.status_code))
        r = user.get("/api/settings/reveal?key=api_key")
        check("API key revealable once signed in", r.status_code == 200, str(r.status_code))

        r = user.get("/logout")
        check("logout redirects", r.status_code == 303, str(r.status_code))

    print("\n=== 5. A forged cookie is rejected ===")
    with TestClient(app, follow_redirects=False) as forger:
        forger.cookies.set("nudnik_session", "admin.FAKE.SIGNATURE")
        r = forger.get("/api/reminders")
        check("tampered cookie refused", r.status_code == 401, str(r.status_code))

    print("\n" + "=" * 58)
    if failures:
        print(f"FAILED {len(failures)}")
        return 1
    print("Auth gate verified: closed to strangers, open to notifications.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
