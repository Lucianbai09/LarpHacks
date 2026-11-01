import os
import re
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask
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
# Memory is fine for one server. Point storage_uri at Redis to run more than one.
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def create_app():
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
    # Email links are a trip to your inbox, so stay logged in between visits.
    app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
    # Tokens last as long as the session, so a page left open keeps working.
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    app.config["BREVO_API_KEY"] = os.environ.get("BREVO_API_KEY")
    app.config["EMAIL_FROM"] = os.environ.get("EMAIL_FROM")
    app.config["APP_URL"] = os.environ.get("RENDER_EXTERNAL_URL", "http://127.0.0.1:5000")

    # Render sets RENDER and serves over HTTPS behind its own proxy. Local runs are plain HTTP.
    if "RENDER" in os.environ:
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["REMEMBER_COOKIE_SECURE"] = True
        app.wsgi_app = ProxyFix(app.wsgi_app)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from . import auth, demo, models, views

    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)

    @app.cli.command("init-db")
    def init_db():
        """Create missing tables and seed data. Safe to re-run."""
        models.init_db()

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add demo accounts and posts. Safe to re-run."""
        demo.seed()

    return app
