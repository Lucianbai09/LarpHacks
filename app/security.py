import json
import urllib.parse
import urllib.request

from flask import current_app, request

from . import client_ip

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Only our own files and Cloudflare's captcha can run, so injected HTML can't execute scripts.
# Styles and fonts also come from Google Fonts. Inline style="" attributes are blocked, so use classes.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://challenges.cloudflare.com; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    # blob: is the preview of a photo you've picked but not posted yet.
    "img-src 'self' blob:; "
    "frame-src https://challenges.cloudflare.com; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def password_problem(password):
    # There are no password rules on purpose, because this is a demo. A blank one just isn't a password.
    return None if password else "Please enter a password."


def captcha_passed():
    """Asks Cloudflare whether this form came from a person. Off when no key is set."""
    secret = current_app.config["TURNSTILE_SECRET_KEY"]
    if not secret:
        return True

    data = urllib.parse.urlencode(
        {
            "secret": secret,
            "response": request.form.get("cf-turnstile-response", ""),
            "remoteip": client_ip(),
        }
    ).encode()
    try:
        with urllib.request.urlopen(TURNSTILE_VERIFY_URL, data=data, timeout=5) as response:  # nosec B310
            return json.load(response).get("success") is True
    except (OSError, ValueError) as error:
        current_app.logger.error("Couldn't check the captcha: %s", error)
        return False


def add_security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    # Other sites never see our URLs, which can hold password reset tokens.
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if current_app.config.get("SESSION_COOKIE_SECURE"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response
