"""Send a real email through a throwaway SMTP server.

Verifies the whole path -- MIME assembly, Hebrew encoding, the HTML body and
its action buttons -- without needing real credentials. If this passes, the
only thing left for a real send is your host, user and app password.

Run: python scripts/test_email.py
"""
import os
import socket
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="nudnik-mail-"))
os.environ["DATABASE_URL"] = "sqlite:///" + os.environ["DATA_DIR"] + "/t.db"
os.environ["SCHEDULER_ENABLED"] = "false"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from app import channels, settings_store  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402

received: list[str] = []


def fake_smtp(port: int, ready: threading.Event) -> None:
    """The smallest SMTP server that will satisfy smtplib."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    ready.set()

    conn, _ = srv.accept()
    conn.sendall(b"220 localhost fake\r\n")
    buf = b""
    in_data = False
    body: list[bytes] = []

    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk

        if in_data:
            body.append(chunk)
            if b"\r\n.\r\n" in b"".join(body):
                received.append(b"".join(body).decode("utf-8", "replace"))
                conn.sendall(b"250 OK queued\r\n")
                in_data = False
                buf = b""
            continue

        while b"\r\n" in buf:
            line, buf = buf.split(b"\r\n", 1)
            cmd = line.decode("utf-8", "replace").upper()
            if cmd.startswith("EHLO") or cmd.startswith("HELO"):
                conn.sendall(b"250-localhost\r\n250 AUTH LOGIN PLAIN\r\n")
            elif cmd.startswith("AUTH"):
                conn.sendall(b"235 authenticated\r\n")
            elif cmd.startswith("MAIL FROM") or cmd.startswith("RCPT TO"):
                conn.sendall(b"250 OK\r\n")
            elif cmd.startswith("DATA"):
                conn.sendall(b"354 send data\r\n")
                in_data = True
                break
            elif cmd.startswith("QUIT"):
                conn.sendall(b"221 bye\r\n")
                conn.close()
                srv.close()
                return
            else:
                conn.sendall(b"250 OK\r\n")


def main() -> int:
    port = 2526
    ready = threading.Event()
    threading.Thread(target=fake_smtp, args=(port, ready), daemon=True).start()
    ready.wait(5)

    init_db()
    db = SessionLocal()
    settings_store.bootstrap(db)
    settings_store.set_value(db, "email_enabled", True)
    settings_store.set_value(db, "smtp_host", "127.0.0.1")
    settings_store.set_value(db, "smtp_port", port)
    settings_store.set_value(db, "smtp_user", "me@example.com")
    settings_store.set_value(db, "smtp_pass", "app-password")
    settings_store.set_value(db, "email_to", "me@example.com")
    settings_store.set_value(db, "smtp_tls", False)  # no TLS on the fake server
    settings_store.invalidate()

    msg = channels.Message(
        title="💊 להתקשר למרפאה ולהזמין את התרופה",
        body="לקחת את התרופה\nפתוח כבר 4 ימים\nביקשתי ממך 7 פעמים",
        occurrence_id=42,
        tier=3,
        links={
            "done": "https://nudnik.example.com/a/tok-done",
            "snooze_tomorrow": "https://nudnik.example.com/a/tok-snooze",
            "open": "https://nudnik.example.com/",
        },
        contact_phone="03-6100000",
        tally=7,
        lang="he",
    )

    ok, detail = channels.send_email(db, msg)
    print(f"  send_email -> ok={ok}  detail={detail}")

    failures = []

    def check(label, cond, extra=""):
        print(("  PASS  " if cond else "  FAIL  ") + label + (f"  [{extra}]" if extra else ""))
        if not cond:
            failures.append(label)

    check("SMTP accepted the message", ok, detail)
    check("server received exactly one mail", len(received) == 1, str(len(received)))

    raw = received[0] if received else ""

    # MIMEText with a utf-8 charset base64-encodes the payload, so the parts
    # have to be decoded before any of this can be checked.
    import email as email_mod
    from email.header import decode_header

    parsed = email_mod.message_from_string(raw)
    parts = {}
    for part in parsed.walk():
        ctype = part.get_content_type()
        if ctype.startswith("text/"):
            parts[ctype] = part.get_payload(decode=True).decode("utf-8", "replace")

    html = parts.get("text/html", "")
    plain = parts.get("text/plain", "")

    subject_raw = parsed.get("Subject", "")
    subject = "".join(
        (chunk.decode(enc or "utf-8", "replace") if isinstance(chunk, bytes) else chunk)
        for chunk, enc in decode_header(subject_raw)
    )

    check("subject decodes to the Hebrew title", "התרופה" in subject, subject[:40])
    check("HTML part present", bool(html))
    check("plain-text part present", bool(plain))
    check("Done action link included", "tok-done" in html)
    check("Snooze action link included", "tok-snooze" in html)
    check("click-to-call included", "tel:03-6100000" in html)
    check("RTL direction set for Hebrew", 'dir="rtl"' in html)
    check("Hebrew body survives round-trip", "לקחת את התרופה" in html)
    check("nag tally shown in the mail", "7" in html)

    db.close()
    print("\n" + "=" * 56)
    if failures:
        print(f"FAILED {len(failures)}")
        return 1
    print("Email path verified. Only real credentials remain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
