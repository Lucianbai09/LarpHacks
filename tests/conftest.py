import os
import re
import types

import pytest
from dotenv import load_dotenv

from helpers import Browser

load_dotenv()
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/larphacks_test")

# These tests wipe the database they run on, so never let them near a real one.
if not re.search(r"_test(\?|$)", TEST_DATABASE_URL):
    raise pytest.UsageError("TEST_DATABASE_URL must point at a database whose name ends in _test.")

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("SECRET_KEY", "only-for-tests")

from app import create_app, db, limiter  # noqa: E402
from app.models import User, init_db  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return create_app(
        {
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
            "EMAIL_WEBHOOK_URL": None,
            "TURNSTILE_SITE_KEY": None,
            "TURNSTILE_SECRET_KEY": None,
            "APP_URL": "https://larphacks.test",
        }
    )


@pytest.fixture(autouse=True)
def clean_database(app):
    limiter.enabled = False
    with app.app_context():
        db.session.remove()
        db.drop_all()
        init_db()
    yield
    with app.app_context():
        db.session.remove()


@pytest.fixture
def visitor(app):
    """Makes logged-out browsers."""
    return lambda: Browser(app)


@pytest.fixture
def make_user(visitor):
    """Registers a real account and returns its logged-in browser."""

    def make(username, **kwargs):
        browser = visitor()
        response = browser.register(username, **kwargs)
        assert response.status_code == 302, response.get_data(as_text=True)
        return browser

    return make


@pytest.fixture
def get_user(app):
    def get(username):
        with app.app_context():
            user = db.session.scalar(db.select(User).filter_by(username=username))
            if user:
                db.session.expunge(user)
            return user

    return get


@pytest.fixture
def count(app):
    def count_rows(model):
        with app.app_context():
            return db.session.scalar(db.select(db.func.count()).select_from(model))

    return count_rows


@pytest.fixture
def post_id(app):
    from app.models import Post

    def find(body):
        with app.app_context():
            return db.session.scalar(db.select(Post.id).filter_by(body=body))

    return find


@pytest.fixture
def seeded(app):
    from app.demo import seed

    with app.app_context():
        seed()


class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def outbox(app, monkeypatch):
    """Turns email on and captures messages instead of sending them."""
    sent = []

    def capture(webhook_url, to, subject, body, logger):
        link = re.search(r"https?://\S+", body)
        sent.append(types.SimpleNamespace(to=to, subject=subject, body=body, path=link.group(0).replace(app.config["APP_URL"], "") if link else None, url=link.group(0) if link else None))

    monkeypatch.setitem(app.config, "EMAIL_WEBHOOK_URL", "https://script.test/exec")
    monkeypatch.setattr("app.mail.deliver", capture)
    monkeypatch.setattr("app.mail.threading", types.SimpleNamespace(Thread=ImmediateThread))
    return sent
