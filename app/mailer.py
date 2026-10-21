"""Sends e-mails through Brevo's web API (free plan: 300 e-mails a day).
Render's free plan blocks normal SMTP ports, so the web API (HTTPS) is used instead.

Settings (environment variables):
  BREVO_API_KEY   the API key from Brevo (starts with xkeysib-)
  MAIL_FROM       the sender address you verified in Brevo
  MAIL_FROM_NAME  optional, default "DiabeCare"
When BREVO_API_KEY or MAIL_FROM is missing, no e-mail is sent: e-mail verification is switched off and
reset codes are only printed in the server console (handy on your own computer)."""
import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.brevo.com/v3/smtp/email"


def mail_configured() -> bool:
    return bool(os.environ.get("BREVO_API_KEY") and os.environ.get("MAIL_FROM"))


def send_mail(to: str, subject: str, text: str) -> bool:
    """True when the mail service accepted the message."""
    if not mail_configured():
        print(f"[mail not configured] to={to} subject={subject!r}\n{text}")
        return False
    payload = json.dumps({
        "sender": {"name": os.environ.get("MAIL_FROM_NAME", "DiabeCare"), "email": os.environ["MAIL_FROM"]},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=payload, headers={
        "api-key": os.environ["BREVO_API_KEY"], "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "DiabeCare/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        print(f"[mail] Brevo refused the message: HTTP {e.code}")      # never print the key or the code
        return False
    except Exception as e:                                            # network problem, timeout, ...
        print(f"[mail] could not reach Brevo: {type(e).__name__}")
        return False