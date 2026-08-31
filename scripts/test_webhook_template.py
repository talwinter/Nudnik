"""Webhook body templating.

Confirms that one webhook channel can produce any third-party API's payload
shape, and that a reminder title containing quotes or newlines cannot break
the JSON.

Run: python scripts/test_webhook_template.py
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="nudnik-hook-"))
os.environ["DATABASE_URL"] = "sqlite:///" + os.environ["DATA_DIR"] + "/t.db"
os.environ["SCHEDULER_ENABLED"] = "false"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import channels, settings_store  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402

captured: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            captured.append(json.loads(raw.decode("utf-8")))
        except json.JSONDecodeError:
            captured.append({"__raw__": raw.decode("utf-8", "replace")})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


failures = []


def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{extra}]" if extra else ""))
    if not cond:
        failures.append(label)


def main() -> int:
    srv = HTTPServer(("127.0.0.1", 8799), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    init_db()
    db = SessionLocal()
    settings_store.bootstrap(db)
    settings_store.set_value(db, "webhook_enabled", True)
    settings_store.set_value(db, "webhook_url", "http://127.0.0.1:8799/hook")
    settings_store.invalidate()

    # A title that would break naive string interpolation: quotes, a newline,
    # a backslash and RTL text.
    nasty_title = 'לקחת "את" התרופה\\now'
    msg = channels.Message(
        title=nasty_title,
        body="פתוח כבר 4 ימים",
        occurrence_id=42,
        links={"done": "https://nudnik.example.com/a/tok"},
        tally=7,
        lang="he",
    )

    print("\n=== 1. Default payload (Discord / Slack / generic) ===")
    ok, detail = channels.send_webhook(db, msg)
    check("sent", ok, detail)
    body = captured[-1]
    check("carries Discord's 'content'", "content" in body)
    check("carries Slack's 'text'", "text" in body)
    check("carries the action links", "done" in (body.get("links") or {}))

    print("\n=== 2. GreenAPI-shaped template ===")
    template = (
        '{"chatId":"972501234567@c.us",'
        '"message":"{{title}}\\n{{body}}\\n\\n\\u2705 {{done_url}}"}'
    )
    settings_store.set_value(db, "webhook_template", template)
    settings_store.invalidate()

    ok, detail = channels.send_webhook(db, msg)
    check("sent", ok, detail)
    body = captured[-1]
    check("payload is exactly the shape the API expects",
          set(body.keys()) == {"chatId", "message"}, str(list(body.keys())))
    check("chatId preserved", body.get("chatId") == "972501234567@c.us")
    check("title substituted", "לקחת" in body.get("message", ""))
    check("quotes in the title survived", '"את"' in body.get("message", ""))
    check("done link substituted", "tok" in body.get("message", ""))
    print("    message ->", repr(body.get("message", ""))[:96])

    print("\n=== 3. A broken template fails loudly, not silently ===")
    settings_store.set_value(db, "webhook_template", '{"oops": }')
    settings_store.invalidate()
    ok, detail = channels.send_webhook(db, msg)
    check("reports the error instead of sending garbage", not ok)
    check("error names the cause", "not valid JSON" in detail, detail[:60])

    db.close()
    srv.shutdown()

    print("\n" + "=" * 56)
    if failures:
        print(f"FAILED {len(failures)}")
        return 1
    print("Webhook templating verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
