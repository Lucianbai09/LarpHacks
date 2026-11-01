import os
import re
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
csrf = CSRFProtect()


def client_ip():
    # Render's traffic comes through Cloudflare, which overwrites this header, so visitors can't fake it.
    # Without it, everyone looks like the same proxy and shares one rate limit.
    return ("RENDER" in os.environ and request.headers.get("CF-Connecting-IP")) or get_remote_address()


# Anything that changes data is limited by default, including routes added later.
# Memory is fine for one server. Point storage_uri at Redis to run more than one.
limiter = Limiter(
    key_func=client_ip,
    storage_uri="memory://",
    default_limits=["60 per minute"],
    default_limits_exempt_when=lambda: request.method in ("GET", "HEAD", "OPTIONS"),
)


def create_app(config=None):
    # The project's .env wins over any DATABASE_URL set globally on the machine.
    load_dotenv(override=True)

    app = Flask(__name__)
    # Render's URLs say plain postgresql://, but psycopg is the driver we install.
    app.config["SQLALCHEMY_DATABASE_URI"] = re.sub(
        r"^postgres(ql)?://", "postgresql+psycopg://", os.environ["DATABASE_URL"]
    )
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
    # Tokens last as long as the session, so a page left open keeps working.
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    # Room for one 10 MB photo and its form. Flask separately caps the text in a form at 500 KB.
    app.config["MAX_CONTENT_LENGTH"] = 11 * 1024 * 1024
    app.config["EMAIL_WEBHOOK_URL"] = os.environ.get("EMAIL_WEBHOOK_URL")
    app.config["TURNSTILE_SITE_KEY"] = os.environ.get("TURNSTILE_SITE_KEY")
    app.config["TURNSTILE_SECRET_KEY"] = os.environ.get("TURNSTILE_SECRET_KEY")
    app.config["APP_URL"] = os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:5000")

    # Render sets RENDER and serves over HTTPS behind its own proxy. Local runs are plain HTTP.
    if "RENDER" in os.environ:
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["REMEMBER_COOKIE_SECURE"] = True
        app.wsgi_app = ProxyFix(app.wsgi_app)

    app.config.update(config or {})

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from . import auth, demo, models, security, views

    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)
    app.after_request(security.add_security_headers)

    @app.cli.command("init-db")
    def init_db():
        """Create missing tables and seed data. Safe to re-run."""
        models.init_db()

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add demo accounts and posts. Never touches real accounts. Safe to re-run."""
        demo.seed()

    @app.cli.command("clear-demo")
    def clear_demo():
        """Delete demo accounts and everything attached to them. Real accounts stay."""
        demo.clear()

    @app.cli.command("reset-demo")
    def reset_demo():
        """Create missing tables, then replace the demo data with a fresh copy. Real accounts stay."""
        models.init_db()
        demo.clear()
        demo.seed()

    return app
