import json
import urllib.parse
import urllib.request

from flask import current_app, request

MIN_PASSWORD_LENGTH = 6

# The passwords attackers try first. Anything else only has to be long enough.
COMMON_PASSWORDS = {
    "000000", "111111", "123123", "123456", "1234567", "12345678", "123456789", "1234567890",
    "1q2w3e4r", "654321", "abc123", "abcdef", "admin123", "asdfgh", "baseball", "dragon",
    "football", "iloveyou", "larphacks", "letmein", "monkey", "passw0rd", "password", "password1",
    "password123", "princess", "qwerty", "qwerty123", "qwertyuiop", "sunshine", "trustno1", "welcome",
}  # fmt: skip

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Only our own files and Cloudflare's captcha can run, so injected HTML can't execute scripts.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://challenges.cloudflare.com; "
    "frame-src https://challenges.cloudflare.com; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def password_problem(password):
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Passwords need at least {MIN_PASSWORD_LENGTH} characters."
    if password.lower() in COMMON_PASSWORDS:
        return "That password is too common, so it's the first one a bot would try."
    return None


def captcha_passed():
    """Asks Cloudflare whether this form came from a person. Off when no key is set."""
    secret = current_app.config["TURNSTILE_SECRET_KEY"]
    if not secret:
        return True

    data = urllib.parse.urlencode(
        {
            "secret": secret,
            "response": request.form.get("cf-turnstile-response", ""),
            "remoteip": request.remote_addr,
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
