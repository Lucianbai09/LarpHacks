import os
import re

from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
csrf = CSRFProtect()


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
    # Render sets RENDER and serves over HTTPS. Local runs are plain HTTP.
    app.config["SESSION_COOKIE_SECURE"] = "RENDER" in os.environ
    # Tokens last as long as the session, so a page left open keeps working.
    app.config["WTF_CSRF_TIME_LIMIT"] = None

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

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
