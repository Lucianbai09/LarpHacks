import json
import threading
import urllib.error
import urllib.request

from flask import current_app, flash

# Brevo's web API, because Render's free plan blocks SMTP. To switch provider, change deliver().
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def deliver(api_key, sender, to, subject, body, logger):
    payload = {
        "sender": {"name": "LarpHacks", "email": sender},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    request = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode(),
        headers={"api-key": api_key, "content-type": "application/json", "accept": "application/json"},
    )
    try:
        urllib.request.urlopen(request, timeout=10).close()
    except urllib.error.HTTPError as error:
        logger.error("Brevo rejected an email: %s %s", error.code, error.read()[:300])
    except OSError as error:
        logger.error("Couldn't reach Brevo: %s", error)


def send_link_email(to, subject, intro, link):
    """Sends in the background, so response times don't reveal which emails have accounts."""
    api_key = current_app.config["BREVO_API_KEY"]
    sender = current_app.config["EMAIL_FROM"]

    if api_key and sender:
        body = f"{intro}\n\n{link}\n\nThis link works once and expires in 1 hour. If this wasn't you, ignore this email."
        args = (api_key, sender, to, subject, body, current_app.logger)
        threading.Thread(target=deliver, args=args, daemon=True).start()
    elif current_app.debug:
        # Local runs work with no email account. Debug is never on in production, so links can't leak there.
        flash(f"Email isn't set up on this computer, so here's the link instead: {link}")
    else:
        current_app.logger.error("Can't send email: BREVO_API_KEY and EMAIL_FROM aren't set.")
