import html
import json
import re
import threading
import urllib.request

from flask import current_app, flash


def page_text(page):
    without_code = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", without_code))).strip()


def deliver(webhook_url, to, subject, body, logger):
    # Calls a small Google Apps Script that sends from a Gmail account for free (see the README).
    # It's a web request because Render's free plan blocks SMTP. To switch provider, change this.
    payload = {"to": to, "subject": subject, "body": body}
    request = urllib.request.Request(
        webhook_url, data=json.dumps(payload).encode(), headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            reply = response.read(20000).decode(errors="replace")
    except OSError as error:
        logger.error("Couldn't reach the email script: %s", error)
        return
    # Apps Script reports its errors as an ordinary web page, not an error status.
    if reply != "sent":
        logger.error("The email script didn't send the email: %s", page_text(reply)[:300])


def send_link_email(to, subject, intro, link):
    """Sends in the background, so response times don't reveal which emails have accounts."""
    webhook_url = current_app.config["EMAIL_WEBHOOK_URL"]

    if webhook_url:
        body = f"{intro}\n\n{link}\n\nIf this wasn't you, you can ignore this email."
        args = (webhook_url, to, subject, body, current_app.logger)
        threading.Thread(target=deliver, args=args, daemon=True).start()
    elif not current_app.debug:
        current_app.logger.error("Can't send email: EMAIL_WEBHOOK_URL isn't set.")

    # Local testing never gets stuck on email. Debug is never on in production, so links can't leak there.
    if current_app.debug:
        flash(f"Running locally, so here's the link in case the email doesn't arrive: {link}")
