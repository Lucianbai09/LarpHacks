import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .models import User

bp = Blueprint("auth", __name__)

USERNAME_PATTERN = re.compile(r"[a-z0-9_]{3,30}")
MIN_PASSWORD_LENGTH = 8


def back(fallback):
    """The `next` path sent with a request, only ever a page on this site."""
    target = request.values.get("next", "")
    return target if re.fullmatch(r"/(?![/\\])[^\s\\]*", target) else fallback


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    username = request.form.get("username", "").strip().lower()
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")

        if not USERNAME_PATTERN.fullmatch(username):
            error = "Usernames are 3-30 letters, numbers or underscores."
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f"Passwords need at least {MIN_PASSWORD_LENGTH} characters."
        elif db.session.scalar(db.select(User).filter_by(username=username)):
            error = "That username is taken."
        else:
            user = User(username=username, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("You're in. Join what you're quitting to start your count.")
            return redirect(url_for("main.category_list"))

    page = render_template("register.html", username=username, min_password_length=MIN_PASSWORD_LENGTH, error=error)
    return page, 400 if error else 200


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    username = request.form.get("username", "").strip().lower()
    error = None

    if request.method == "POST":
        user = db.session.scalar(db.select(User).filter_by(username=username))
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            login_user(user)
            return redirect(back(url_for("main.home")))
        error = "Wrong username or password."

    page = render_template("login.html", username=username, error=error)
    return page, 401 if error else 200


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.home"))
