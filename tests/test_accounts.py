import threading

import pytest

from app import auth
from app.models import TERMS_VERSION, CheckIn, CircleLink, Comment, Membership, Post, Reaction, User
from helpers import PASSWORD


@pytest.mark.parametrize(
    "username, email, password, terms",
    [
        ("ab", "a@mail.test", PASSWORD, True),
        ("has space", "a@mail.test", PASSWORD, True),
        ("<b>hi", "a@mail.test", PASSWORD, True),
        ("goodname", "", PASSWORD, True),
        ("goodname", "nope", PASSWORD, True),
        ("goodname", "a@b", PASSWORD, True),
        ("goodname", "a b@mail.test", PASSWORD, True),
        ("goodname", "a" * 250 + "@mail.test", PASSWORD, True),
        ("goodname", "a@mail.test", "", True),
        ("goodname", "a@mail.test", PASSWORD, False),
    ],
)
def test_register_rejects_bad_input(visitor, count, username, email, password, terms):
    assert visitor().register(username, email, password, terms).status_code == 400
    assert count(User) == 0


def test_register_keeps_typed_values_but_not_the_password(visitor):
    html = visitor().register("keepme", "keep@mail.test", terms=False).get_data(as_text=True)
    assert 'value="keepme"' in html and 'value="keep@mail.test"' in html
    assert PASSWORD not in html


def test_register_creates_a_logged_in_account(visitor, get_user):
    browser = visitor()
    response = browser.register("Author", "Author@Mail.test", "aaaaaa")
    assert response.status_code == 302 and response.headers["Location"] == "/categories"
    assert browser.logged_in()
    user = get_user("author")
    assert user.email == "author@mail.test"
    assert user.password_hash.startswith("scrypt:") and "aaaaaa" not in user.password_hash
    assert user.terms_version == TERMS_VERSION and user.terms_accepted_at
    assert user.is_demo is False and user.email_verified_at is None


def test_one_account_per_email(visitor, make_user, count):
    make_user("author", email="author@mail.test")
    for email in ["author@mail.test", "AUTHOR@mail.TEST"]:
        response = visitor().register("different", email)
        assert response.status_code == 400 and b"already has an account" in response.data
    assert visitor().register("AUTHOR", "fresh@mail.test").status_code == 400
    assert count(User) == 1


def test_double_submit_makes_one_account_and_no_crash(visitor, count):
    browsers = [visitor() for _ in range(8)]
    tokens = [b.token("/register") for b in browsers]
    codes = [None] * 8
    gate = threading.Barrier(8)

    def submit(i):
        gate.wait()
        data = {"csrf_token": tokens[i], "username": "racer", "email": "racer@mail.test", "password": PASSWORD, "terms": "on"}
        codes[i] = browsers[i].c.post("/register", data=data).status_code

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes.count(302) == 1 and codes.count(400) == 7, codes
    assert count(User) == 1


@pytest.mark.parametrize("identifier", ["author", "AUTHOR", "author@mail.test", "AUTHOR@MAIL.TEST"])
def test_login_with_username_or_email(make_user, visitor, identifier):
    make_user("author")
    browser = visitor()
    assert browser.login(identifier).status_code == 302 and browser.logged_in()


def test_failed_logins_look_the_same(make_user, visitor):
    make_user("author")
    wrong = visitor().login("author", "wrongpass")
    unknown = visitor().login("ghost", "wrongpass")
    assert wrong.status_code == unknown.status_code == 401
    assert b"Wrong username, email or password" in wrong.data and b"Wrong username, email or password" in unknown.data


def test_login_returns_to_the_page_you_wanted(make_user, visitor):
    make_user("author")
    assert visitor().login("author", path="/login?next=/write").headers["Location"] == "/write"


@pytest.mark.parametrize("evil", ["//evil.test", "https://evil.test", "/%5Cevil.test", "/%09/evil.test", "%2F%2Fevil.test"])
def test_login_never_redirects_offsite(make_user, visitor, evil):
    make_user("author")
    assert visitor().login("author", path=f"/login?next={evil}").headers["Location"] == "/"


def test_staying_logged_in_and_logging_out(make_user, visitor):
    make_user("author")
    browser = visitor()
    response = browser.login("author")
    cookie = [v for v in response.headers.getlist("Set-Cookie") if v.startswith("remember_token")]
    assert cookie and "HttpOnly" in cookie[0]
    browser.c.delete_cookie("session")
    assert browser.logged_in()
    browser.logout()
    assert not browser.logged_in() and browser.c.get_cookie("remember_token") is None


def test_changing_password_logs_out_other_devices(make_user, visitor):
    phone = make_user("author")
    laptop = visitor()
    laptop.login("author")
    assert "Password saved" in phone.set_password("changed1").get_data(as_text=True)
    assert phone.logged_in() and not laptop.logged_in()
    assert visitor().login("author", PASSWORD).status_code == 401
    assert visitor().login("author", "changed1").status_code == 302


def test_any_password_works_except_a_blank_one(make_user, visitor):
    browser = make_user("author")
    assert "enter a password" in browser.set_password("").get_data(as_text=True)
    assert "Password saved" in browser.set_password("a").get_data(as_text=True)
    assert visitor().register("newbie", password="password").status_code == 302


# ---- Email confirmation


def test_register_sends_a_confirmation_link(make_user, outbox):
    make_user("author", email="Author@mail.test")
    assert len(outbox) == 1 and outbox[0].to == "author@mail.test"
    assert outbox[0].url.startswith("https://larphacks.test/confirm-email/")


def test_email_confirmation(make_user, visitor, outbox, get_user):
    browser = make_user("author")
    path = outbox[0].path
    assert "not confirmed" not in browser.text("/u/author")
    assert "<small" not in browser.text("/u/author").split("</h1>")[0]

    for _ in range(3):
        assert visitor().c.get(path).status_code == 200
    assert get_user("author").email_verified_at is None, "mail scanners opening the link must not confirm it"

    response = visitor().post(path, token_from=path, follow_redirects=True)
    assert b"Your email is confirmed" in response.data
    assert get_user("author").email_verified_at is not None
    assert 'title="Email confirmed"' in visitor().text("/u/author")
    assert "Your email is confirmed" in browser.text("/account")


def test_bad_confirmation_links_do_nothing(make_user, visitor, outbox, get_user, monkeypatch):
    make_user("author")
    path = outbox[0].path
    for bad in [path[:-3] + "abc", "/confirm-email/not-a-token"]:
        assert visitor().post(bad).status_code == 302
    monkeypatch.setattr(auth, "CONFIRM_MAX_AGE_SECONDS", -1)
    assert visitor().post(path).status_code == 302
    assert get_user("author").email_verified_at is None


def test_resend_confirmation(make_user, outbox):
    browser = make_user("author")
    assert "Send confirmation link" in browser.text("/account")
    browser.post("/account/confirm-email")
    assert len(outbox) == 2
    browser.post(outbox[1].path, token_from=outbox[1].path)
    browser.post("/account/confirm-email")
    assert len(outbox) == 2, "nothing to resend once it's confirmed"


def test_unconfirmed_accounts_still_work(make_user):
    browser = make_user("author")
    assert browser.write("Still works").status_code == 302


# ---- Password reset


def test_reset_password_journey(make_user, visitor, outbox, get_user):
    make_user("author")
    outbox.clear()
    response = visitor().post("/forgot-password", {"email": "AUTHOR@mail.test"}, follow_redirects=True)
    assert b"If that email has an account" in response.data
    assert len(outbox) == 1 and outbox[0].url.startswith("https://larphacks.test/reset-password/")

    path = outbox[0].path
    for _ in range(3):
        assert visitor().c.get(path).status_code == 200
    assert visitor().login("author").status_code == 302, "opening the link must not change anything"

    assert visitor().post(path, {"password": ""}, token_from=path).status_code == 400
    browser = visitor()
    assert browser.post(path, {"password": "brandnew"}, token_from=path).status_code == 302
    assert browser.logged_in()
    assert visitor().login("author", PASSWORD).status_code == 401
    assert visitor().login("author", "brandnew").status_code == 302
    assert get_user("author").email_verified_at is not None, "using the link proves the email is theirs"


def test_reset_links_work_once(make_user, visitor, outbox):
    make_user("author")
    outbox.clear()
    visitor().post("/forgot-password", {"email": "author@mail.test"})
    path = outbox[0].path
    visitor().post(path, {"password": "brandnew"}, token_from=path)
    assert visitor().post(path, {"password": "hijacked1"}).headers["Location"] == "/forgot-password"
    assert visitor().login("author", "hijacked1").status_code == 401


def test_reset_links_die_when_the_password_changes(make_user, visitor, outbox):
    browser = make_user("author")
    outbox.clear()
    visitor().post("/forgot-password", {"email": "author@mail.test"})
    browser.set_password("changed1")
    assert visitor().post(outbox[0].path, {"password": "hijacked1"}).headers["Location"] == "/forgot-password"
    assert visitor().login("author", "hijacked1").status_code == 401


def test_reset_rejects_bad_expired_and_mixed_up_tokens(make_user, visitor, outbox, monkeypatch):
    browser = make_user("author")
    confirm_path = outbox[0].path
    outbox.clear()
    visitor().post("/forgot-password", {"email": "author@mail.test"})
    path = outbox[0].path

    assert visitor().post(path[:-3] + "abc", {"password": "hijacked1"}).status_code == 302
    token = confirm_path.rsplit("/", 1)[1]
    assert visitor().post(f"/reset-password/{token}", {"password": "hijacked1"}).status_code == 302, "a confirmation link can't reset a password"
    monkeypatch.setattr(auth, "RESET_MAX_AGE_SECONDS", -1)
    assert visitor().post(path, {"password": "hijacked1"}).status_code == 302
    assert visitor().login("author", "hijacked1").status_code == 401
    assert browser.logged_in()


def test_forgot_password_never_reveals_who_has_an_account(make_user, visitor, outbox):
    make_user("author")
    outbox.clear()
    known = visitor().post("/forgot-password", {"email": "author@mail.test"})
    assert len(outbox) == 1
    unknown = visitor().post("/forgot-password", {"email": "stranger@mail.test"})
    assert len(outbox) == 1, "nothing goes to an unknown address"
    assert (known.status_code, known.headers["Location"]) == (unknown.status_code, unknown.headers["Location"])


def test_forgot_password_says_so_when_email_is_off(visitor):
    assert "aren&#39;t available" in visitor().text("/forgot-password") or "aren't available" in visitor().text("/forgot-password")


def test_forgot_password_sends_logged_in_people_to_their_account(make_user):
    assert make_user("author").c.get("/forgot-password").headers["Location"] == "/account"


def test_emails_never_mention_what_someone_is_quitting(make_user, visitor, outbox):
    make_user("author")
    visitor().post("/forgot-password", {"email": "author@mail.test"})
    assert len(outbox) == 2
    for message in outbox:
        text = (message.subject + message.body).lower()
        assert not any(word in text for word in ("alcohol", "addict", "sober", "gaming", "scrolling", "quit", "relapse"))


# ---- Private information and leaving


def test_email_is_never_shown_to_anyone_else(make_user, visitor, post_id):
    alice = make_user("alice")
    bobby = make_user("bobby")
    alice.write("hello from alice")
    alice.add("bobby")
    bobby.add("alice")
    for viewer in [visitor(), bobby]:
        for path in ["/", "/u/alice", "/categories/alcohol", f"/posts/{post_id('hello from alice')}"]:
            assert "alice@mail.test" not in viewer.text(path), path
    assert "alice@mail.test" not in bobby.text("/circle")
    assert "alice@mail.test" in alice.text("/account")
    assert "alice@mail.test" not in bobby.text("/account")


def test_account_page_requires_login(visitor):
    assert visitor().c.get("/account").headers["Location"].startswith("/login")


def test_deleting_an_account_removes_only_what_was_theirs(make_user, visitor, app, count, post_id, get_user):
    alice = make_user("alice")
    bobby = make_user("bobby")
    alice.write("hello from alice")
    bobby.write("bobby stays", category="")
    alices, bobbys = post_id("hello from alice"), post_id("bobby stays")
    alice.post(f"/posts/{bobbys}/comment", {"body": "alice on bobby"})
    alice.post(f"/posts/{bobbys}/believe", {"next": "/"})
    bobby.post(f"/posts/{alices}/comment", {"body": "bobby on alice"})
    bobby.post(f"/posts/{alices}/believe", {"next": "/"})
    alice.post("/categories/alcohol/join")
    alice.post("/check-in", {"mood": "4", "urges": "1", "on_track": "yes", "visibility": "private"})
    alice.add("bobby")
    bobby.add("alice")

    assert alice.c.post("/account/delete").status_code == 400, "needs a CSRF token"
    assert alice.c.get("/account/delete").status_code == 405
    assert get_user("alice") is not None

    assert b"have been deleted" in alice.post("/account/delete", follow_redirects=True).data
    assert get_user("alice") is None and not alice.logged_in()
    assert count(User) == 1 and count(Post) == 1 and count(Comment) == 0
    assert count(Reaction) == 0 and count(Membership) == 0 and count(CircleLink) == 0 and count(CheckIn) == 0
    assert "bobby stays" in visitor().text("/") and bobby.logged_in()
    assert visitor().register("alice2", "alice@mail.test").status_code == 302, "the email is free again"
