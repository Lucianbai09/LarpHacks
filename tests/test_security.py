"""Includes rules that scan the whole app, so a new feature that forgets one of them fails here."""
import http.server
import io
import json
import logging
import re
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image

from app import create_app, limiter
from app.mail import deliver, page_text
from app.models import Comment, Post, User
from helpers import PASSWORD

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Pages anyone can open without logging in. A new page is private until it's added here on purpose.
PUBLIC_ENDPOINTS = {
    "static",
    "main.home",
    "main.terms",
    "main.privacy",
    "main.category_list",
    "main.category_feed",
    "main.post_detail",
    "main.post_photo",
    "main.profile",
    "auth.register",
    "auth.login",
    "auth.confirm_email",
    "auth.forgot_password",
    "auth.reset_password",
}

URL_VALUES = {"slug": "alcohol", "token": "not-a-token", "username": "nobody", "post_id": 1, "filename": "style.css", "step": 1}


def routes(app, method=None):
    for rule in app.url_map.iter_rules():
        methods = rule.methods - {"HEAD", "OPTIONS"}
        if method:
            methods &= {method}
        path = app.url_map.bind("localhost").build(rule.endpoint, {arg: URL_VALUES[arg] for arg in rule.arguments})
        for each in methods:
            yield rule.endpoint, each, path


def source(pattern):
    return [(path, path.read_text(encoding="utf-8")) for path in APP_DIR.rglob(pattern)]


# ---- Rules every route must follow, including ones added later


def test_every_route_outside_the_public_list_requires_login(app, monkeypatch):
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    client = app.test_client()
    for endpoint, method, path in routes(app):
        if endpoint in PUBLIC_ENDPOINTS:
            continue
        response = client.open(path, method=method)
        assert response.status_code == 302 and "/login" in response.headers["Location"], f"{method} {path} is open to logged-out visitors"


def test_every_form_submission_requires_a_csrf_token(app):
    client = app.test_client()
    for endpoint, method, path in routes(app, "POST"):
        assert client.post(path).status_code == 400, f"POST {path} accepted a request with no CSRF token"


def test_public_list_has_no_stale_entries(app):
    assert PUBLIC_ENDPOINTS <= {rule.endpoint for rule in app.url_map.iter_rules()}


def test_everything_that_changes_data_is_rate_limited_by_default(make_user, post_id):
    browser = make_user("alice")
    browser.write("a post")
    token = browser.token("/")
    limiter.enabled = True
    limiter.reset()
    try:
        codes = [browser.c.post("/circle/add", data={"csrf_token": token, "username": "ghost"}).status_code for _ in range(61)]
    finally:
        limiter.enabled = False
    assert codes[:60] == [302] * 60 and codes[60] == 429, codes[-3:]


@pytest.mark.parametrize(
    "path, data, first",
    [
        ("/login", {"identifier": "ghost", "password": "wrongpass"}, 401),
        ("/register", {"username": "x", "email": "x", "password": "x"}, 400),
    ],
)
def test_login_and_register_have_stricter_limits(visitor, path, data, first):
    browser = visitor()
    token = browser.token(path)
    limiter.enabled = True
    limiter.reset()
    try:
        codes = [browser.c.post(path, data={"csrf_token": token, **data}).status_code for _ in range(11)]
    finally:
        limiter.enabled = False
    assert codes == [first] * 10 + [429]


def test_email_sending_has_the_strictest_limit(visitor):
    browser = visitor()
    token = browser.token("/login")
    limiter.enabled = True
    limiter.reset()
    try:
        codes = [browser.c.post("/forgot-password", data={"csrf_token": token, "email": "a@mail.test"}).status_code for _ in range(6)]
    finally:
        limiter.enabled = False
    assert codes == [302] * 5 + [429]


def test_reading_pages_is_never_rate_limited(visitor):
    browser = visitor()
    limiter.enabled = True
    limiter.reset()
    try:
        assert all(browser.c.get("/login").status_code == 200 for _ in range(70))
    finally:
        limiter.enabled = False


# ---- Code rules, so unsafe patterns can't slip in


def test_no_raw_sql_anywhere():
    for path, text in source("*.py"):
        assert not re.search(r"\btext\(|\.execute\(\s*f?[\"']|\.format\(.*(SELECT|INSERT|UPDATE|DELETE)", text), f"raw SQL in {path}"


def test_every_query_for_posts_goes_through_visible_to():
    for path, text in source("*.py"):
        for match in re.finditer(r"db\.select\(Post\b", text):
            assert "visible_to" in text[match.start() : match.start() + 220], f"a Post query in {path} skips visible_to()"
    views = (APP_DIR / "views.py").read_text(encoding="utf-8")
    comment_query = views[views.index("db.select(Comment)") :][:220]
    assert "visible_to" in comment_query


def test_no_unsafe_templates_or_html():
    for path, text in source("*.py"):
        assert not re.search(r"render_template_string|Markup\(|\beval\(|\bexec\(", text), f"unsafe call in {path}"
    for path, text in source("*.html"):
        assert "|safe" not in text and "autoescape false" not in text, f"escaping turned off in {path}"
        assert not re.search(r"\son[a-z]+\s*=", text), f"inline event handler in {path}, which the security policy blocks"
        assert not re.search(r"\sstyle\s*=", text), f"style attribute in {path}, which the security policy blocks"
        for script in re.findall(r"<script\b[^>]*>", text):
            assert "src=" in script, f"inline script in {path}, which the security policy blocks"


def test_no_secrets_in_the_code():
    for path, text in source("*.py"):
        assert not re.search(r"postgresql(\+\w+)?://[^:\s\"']+:[^@\s\"']+@", text), f"database password in {path}"
        assert "AKfycb" not in text, f"email script URL in {path}"


def test_debug_mode_is_never_turned_on_inside_the_app():
    for path, text in source("*.py"):
        assert not re.search(r"debug\s*=\s*True|\[.DEBUG.\]\s*=\s*True", text), f"debug turned on in {path}"


# ---- Attacks


INJECTION = ["' OR '1'='1", "' OR 1=1 --", "'; DROP TABLE users; --", '" OR ""="', "admin'--", "' UNION SELECT password_hash FROM users --"]


@pytest.mark.parametrize("payload", INJECTION)
def test_sql_injection_goes_nowhere(make_user, visitor, count, post_id, payload):
    alice = make_user("alice")
    alice.write("target-post", "private")
    alice.post("/categories/alcohol/join")

    assert visitor().login(payload, payload).status_code == 401
    assert visitor().login("alice", payload).status_code == 401
    assert visitor().register(payload, "x@mail.test").status_code == 400
    assert visitor().register("newbie", payload).status_code == 400
    assert visitor().post("/forgot-password", {"email": payload}).status_code == 302
    for path in [f"/u/{payload}", f"/categories/{payload}", f"/posts/{payload}"]:
        assert visitor().c.get(path).status_code == 404, path
    assert b"No one else" in alice.add(payload).data
    assert alice.post("/write", {"body": "x", "visibility": payload, "report_type": "post"}).status_code == 400
    assert alice.post("/write", {"body": "x", "visibility": "public", "report_type": "post", "category": payload}).status_code == 400

    # Stored as plain text, and the tables are still there.
    alice.write(payload, "public")
    assert post_id(payload) is not None
    alice.post(f"/posts/{post_id(payload)}/comment", {"body": payload})
    assert count(User) == 1 and count(Post) == 2 and count(Comment) == 1
    assert "target-post" not in visitor().text("/")


@pytest.mark.parametrize("payload", ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "\"><svg onload=alert(1)>"])
def test_html_in_posts_and_comments_is_shown_as_text(make_user, visitor, post_id, payload):
    alice = make_user("alice")
    alice.write(payload)
    target = post_id(payload)
    alice.post(f"/posts/{target}/comment", {"body": payload})
    for path in ["/", f"/posts/{target}", "/categories/alcohol", "/u/alice"]:
        assert payload not in visitor().text(path), path
    assert "&lt;" in visitor().text(f"/posts/{target}")


def test_faked_host_header_cannot_change_email_links(app, make_user, outbox):
    make_user("alice")
    outbox.clear()
    client = app.test_client()
    html = client.get("/forgot-password", base_url="http://evil.test").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    client.post("/forgot-password", base_url="http://evil.test", data={"csrf_token": token, "email": "alice@mail.test"})
    assert outbox[0].url.startswith("https://larphacks.test/reset-password/"), outbox[0].url


def test_oversized_requests_are_refused(make_user):
    browser = make_user("alice")
    token = browser.token("/")
    response = browser.c.post("/write", data={"csrf_token": token, "body": "x" * (11 * 1024 * 1024 + 1)})
    assert response.status_code == 413


# ---- Photos


def phone_photo():
    """A JPEG with a GPS location in it, like a phone would take."""
    exif = Image.Exif()
    exif.get_ifd(0x8825)[1] = "N"
    output = io.BytesIO()
    Image.new("RGB", (2000, 1000), "orange").save(output, "JPEG", exif=exif)
    assert Image.open(io.BytesIO(output.getvalue())).getexif().get_ifd(0x8825)
    return io.BytesIO(output.getvalue())


def test_photos_lose_their_location_and_follow_the_post_audience(make_user, visitor, post_id):
    alice = make_user("alice")
    stranger = make_user("stranger")
    alice.post("/write", {"body": "circle-photo", "visibility": "circle", "report_type": "reflection", "photo": (phone_photo(), "me.jpg")})
    url = f"/posts/{post_id('circle-photo')}/photo"
    assert url in alice.text("/")

    photo = alice.c.get(url)
    saved = Image.open(io.BytesIO(photo.data))
    assert photo.status_code == 200 and photo.mimetype == "image/jpeg"
    assert not saved.getexif().get_ifd(0x8825), "the location has to go"
    assert max(saved.size) == 1280

    assert visitor().c.get(url).status_code == 404
    assert stranger.c.get(url).status_code == 404
    assert url not in stranger.text("/")


def test_a_photo_can_be_the_whole_post_but_other_files_cannot(make_user, count):
    browser = make_user("alice")
    fields = {"body": "", "visibility": "public", "report_type": "post"}
    for name, junk in [("x.png", b"<script>alert(1)</script>"), ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>"), ("x.jpg", b"")]:
        response = browser.post("/write", {**fields, "photo": (io.BytesIO(junk), name)})
        assert response.status_code == 400, name
    assert count(Post) == 0
    assert browser.post("/write", {**fields, "photo": (phone_photo(), "me.jpg")}).status_code == 302
    assert count(Post) == 1


def test_sessions_from_before_a_password_change_stop_working(make_user, visitor):
    alice = make_user("alice")
    stolen = visitor()
    stolen.login("alice")
    alice.set_password("changed1")
    assert not stolen.logged_in()


# ---- Security headers


@pytest.mark.parametrize("path", ["/", "/login", "/register", "/terms", "/static/style.css"])
def test_security_headers_are_on_every_response(app, path):
    headers = app.test_client().get(path).headers
    policy = headers["Content-Security-Policy"]
    assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy and "object-src 'none'" in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"


def test_hsts_is_only_sent_over_https(app, monkeypatch):
    assert "Strict-Transport-Security" not in app.test_client().get("/").headers
    monkeypatch.setitem(app.config, "SESSION_COOKIE_SECURE", True)
    assert "max-age" in app.test_client().get("/").headers["Strict-Transport-Security"]


# ---- Captcha


class FakeCloudflare:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, url, data=None, timeout=None):
        self.calls.append((url, parse_qs(data.decode())))
        if isinstance(self.reply, Exception):
            raise self.reply
        return io.BytesIO(json.dumps(self.reply).encode())


@pytest.fixture
def captcha_on(app, monkeypatch):
    monkeypatch.setitem(app.config, "TURNSTILE_SITE_KEY", "site-key")
    monkeypatch.setitem(app.config, "TURNSTILE_SECRET_KEY", "secret-key")

    def install(reply):
        cloudflare = FakeCloudflare(reply)
        monkeypatch.setattr("app.security.urllib.request.urlopen", cloudflare)
        return cloudflare

    return install


def test_captcha_is_off_without_keys(visitor):
    assert "cf-turnstile" not in visitor().text("/register")
    assert visitor().register("alice").status_code == 302


def test_captcha_shows_on_register_and_not_on_login(visitor, captcha_on, outbox):
    captcha_on({"success": True})
    assert 'data-sitekey="site-key"' in visitor().text("/register")
    assert 'data-sitekey="site-key"' in visitor().text("/forgot-password")
    assert "cf-turnstile" not in visitor().text("/login"), "password login is covered by rate limits, so the live demo can't get stuck on it"


def test_captcha_token_is_checked_with_cloudflare(visitor, captcha_on, get_user):
    cloudflare = captcha_on({"success": True})
    assert visitor().register("alice", **{"cf-turnstile-response": "token-from-widget"}).status_code == 302
    url, sent = cloudflare.calls[0]
    assert url == "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    assert sent["secret"] == ["secret-key"] and sent["response"] == ["token-from-widget"]
    assert get_user("alice") is not None


@pytest.mark.parametrize("reply", [{"success": False}, {}, OSError("network down"), {"success": "true"}])
def test_register_fails_closed_when_the_captcha_does_not_pass(visitor, captcha_on, get_user, reply):
    captcha_on(reply)
    response = visitor().register("alice")
    assert response.status_code == 400 and b"captcha" in response.data
    assert get_user("alice") is None


def test_forgot_password_needs_the_captcha_too(make_user, visitor, captcha_on, outbox):
    captcha_on({"success": True})
    make_user("alice")
    outbox.clear()
    captcha_on({"success": False})
    response = visitor().post("/forgot-password", {"email": "alice@mail.test"}, token_from="/forgot-password")
    assert response.status_code == 400 and outbox == []


# ---- Email delivery


def test_email_links_never_appear_on_the_page(app, monkeypatch, make_user, visitor):
    make_user("alice")
    monkeypatch.setattr(app, "debug", True)
    monkeypatch.setitem(app.config, "DEBUG", True)
    assert "/reset-password/" not in visitor().post("/forgot-password", {"email": "alice@mail.test"}, follow_redirects=True).get_data(as_text=True)


class FakeAppsScript(http.server.BaseHTTPRequestHandler):
    """Behaves like Google: a POST gets a 302, and the GET it leads to returns the script's output."""

    received = []
    replies = {
        "/exec": "sent",
        "/fail": "<!DOCTYPE html><html><head><style>" + "body {margin: 0;} " * 300 + "</style></head><body><div>Exception: Service invoked too many times (line 3, file &quot;Code&quot;)</div></body></html>",
    }

    def do_POST(self):
        if self.path == "/broken":
            self.send_response(500)
            self.end_headers()
            return
        self.received.append(json.loads(self.rfile.read(int(self.headers["content-length"]))))
        self.send_response(302)
        self.send_header("Location", f"/echo?from={self.path}")
        self.end_headers()

    def do_GET(self):
        reply = self.replies[parse_qs(urlparse(self.path).query)["from"][0]].encode()
        self.send_response(200)
        self.send_header("content-length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


@pytest.fixture
def script_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeAppsScript)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    FakeAppsScript.received.clear()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_deliver_follows_the_redirect_and_stays_quiet_on_success(script_url, caplog):
    deliver(f"{script_url}/exec", "you@mail.test", "Subject", "Body", logging.getLogger("test"))
    assert caplog.records == []
    assert FakeAppsScript.received == [{"to": "you@mail.test", "subject": "Subject", "body": "Body"}]


def test_deliver_logs_a_readable_error_from_the_script(script_url, caplog):
    deliver(f"{script_url}/fail", "you@mail.test", "Subject", "Body", logging.getLogger("test"))
    assert 'Service invoked too many times (line 3, file "Code")' in caplog.text
    assert "margin" not in caplog.text and "<" not in caplog.text


@pytest.mark.parametrize("path", ["/broken"])
def test_deliver_survives_a_server_error(script_url, caplog, path):
    deliver(f"{script_url}{path}", "you@mail.test", "Subject", "Body", logging.getLogger("test"))
    assert "Couldn't reach the email script" in caplog.text


def test_deliver_survives_nothing_listening(caplog):
    deliver("http://127.0.0.1:1/exec", "you@mail.test", "Subject", "Body", logging.getLogger("test"))
    assert "Couldn't reach the email script" in caplog.text


def test_page_text_strips_scripts_styles_and_tags():
    assert page_text("<style>a{}</style><script>x()</script><p>Hello &amp; bye</p>") == "Hello & bye"


# ---- Running on Render


def test_render_settings(monkeypatch, visitor):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://larphacks.onrender.com")
    app = create_app({"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://x@localhost/x_test"})
    assert app.debug is False
    assert app.config["SESSION_COOKIE_SECURE"] is True and app.config["REMEMBER_COOKIE_SECURE"] is True
    assert app.config["APP_URL"] == "https://larphacks.onrender.com"


@pytest.mark.parametrize("given", ["postgres://u:p@h/db", "postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"])
def test_render_database_urls_get_the_right_driver(monkeypatch, given):
    monkeypatch.setenv("DATABASE_URL", given)
    monkeypatch.setattr("app.load_dotenv", lambda **kwargs: None)
    assert create_app().config["SQLALCHEMY_DATABASE_URI"] == "postgresql+psycopg://u:p@h/db"


def test_importing_run_does_not_start_a_dev_server():
    text = (APP_DIR.parent / "run.py").read_text(encoding="utf-8")
    assert re.search(r'if __name__ == "__main__":\s+(#.*\s+)?app\.run\(debug=True', text)
    assert PASSWORD not in text
