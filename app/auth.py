import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, limiter
from .mail import send_link_email
from .models import TERMS_VERSION, User

bp = Blueprint("auth", __name__)

USERNAME_PATTERN = re.compile(r"[a-z0-9_]{3,30}")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MAX_EMAIL_LENGTH = 254
MIN_PASSWORD_LENGTH = 6
LINK_MAX_AGE_SECONDS = 60 * 60

LOGIN_LIMIT = "10 per minute"
EMAIL_LIMIT = "5 per minute;50 per day"

# Checked when no account matches, so response times don't reveal which accounts exist.
DUMMY_PASSWORD_HASH = generate_password_hash("not a real password")


def back(fallback):
    """The `next` path sent with a request, only ever a page on this site."""
    target = request.values.get("next", "")
    return target if re.fullmatch(r"/(?![/\\])[^\s\\]*", target) else fallback


def link_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="email-link")


def email_link(payload):
    # Built from APP_URL, not the request, because a request's Host header can be faked.
    return current_app.config["APP_URL"] + url_for("auth.use_link", token=link_serializer().dumps(payload))


def send_login_link(user, intro):
    link = email_link({"action": "login", "user_id": user.id, "version": user.login_version})
    send_link_email(user.email, "Your LarpHacks login link", intro, link)


def form_email():
    return request.form.get("email", "").strip().lower()


def find_by_email(email):
    return db.session.scalar(db.select(User).filter_by(email=email))


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit(EMAIL_LIMIT, methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    username = request.form.get("username", "").strip().lower()
    email = form_email()
    error = None

    if request.method == "POST":
        if not USERNAME_PATTERN.fullmatch(username):
            error = "Usernames are 3-30 letters, numbers or underscores."
        elif not EMAIL_PATTERN.fullmatch(email) or len(email) > MAX_EMAIL_LENGTH:
            error = "That doesn't look like an email address."
        elif not request.form.get("terms"):
            error = "Please agree to the Terms and Privacy Policy to continue."
        elif db.session.scalar(db.select(User).filter_by(username=username)):
            error = "That username is taken."
        else:
            # The same page either way, so this form can't reveal who has an account here.
            existing = find_by_email(email)
            if existing:
                send_login_link(existing, "Someone, hopefully you, tried to register with this email, but it already has an account. Use this link to log in:")
            else:
                link = email_link({"action": "register", "username": username, "email": email})
                send_link_email(email, "Confirm your LarpHacks account", "Confirm your email to finish creating your account:", link)
            return redirect(url_for("auth.check_email"))

    page = render_template("register.html", username=username, email=email, error=error)
    return page, 400 if error else 200


@bp.route("/check-email")
def check_email():
    return render_template("check_email.html")


@bp.route("/auth/<token>", methods=["GET", "POST"])
def use_link(token):
    invalid = "That link has expired or was already used. Ask for a new one here."
    try:
        link = link_serializer().loads(token, max_age=LINK_MAX_AGE_SECONDS)
    except BadData:
        flash(invalid)
        return redirect(url_for("auth.login"))

    registering = link["action"] == "register"
    user = None
    if not registering:
        user = db.session.get(User, link["user_id"])
        if not user or user.login_version != link["version"]:
            flash(invalid)
            return redirect(url_for("auth.login"))

    # Opening a link only shows a button, because mail scanners open links and would use them up.
    if request.method == "GET":
        return render_template("confirm_link.html", registering=registering)

    if registering:
        user = User(username=link["username"], email=link["email"], terms_version=TERMS_VERSION)
        db.session.add(user)
    else:
        user.login_version += 1

    try:
        db.session.commit()
    except IntegrityError:
        # The link was already used, or someone else took the username in the meantime.
        db.session.rollback()
        flash("That link was already used, or the username has since been taken. Please try again.")
        return redirect(url_for("auth.register"))

    login_user(user, remember=True)
    if registering:
        flash("You're in. Join what you're quitting to start your count.")
        return redirect(url_for("main.category_list"))
    return redirect(url_for("main.home"))


@bp.post("/login/link")
@limiter.limit(EMAIL_LIMIT)
def login_link():
    user = find_by_email(form_email())
    if user:
        send_login_link(user, "Use this link to log in:")
    return redirect(url_for("auth.check_email"))


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(LOGIN_LIMIT, methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    identifier = request.form.get("identifier", "").strip().lower()
    error = None

    if request.method == "POST":
        user = db.session.scalar(db.select(User).where(or_(User.username == identifier, User.email == identifier)))
        stored_hash = user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH
        if check_password_hash(stored_hash, request.form.get("password", "")) and stored_hash != DUMMY_PASSWORD_HASH:
            login_user(user, remember=True)
            return redirect(back(url_for("main.home")))
        error = "Wrong username, email or password."

    page = render_template("login.html", identifier=identifier, error=error)
    return page, 401 if error else 200


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.home"))


@bp.route("/account")
@login_required
def account():
    return render_template("account.html", min_password_length=MIN_PASSWORD_LENGTH)


@bp.post("/account/password")
@login_required
def set_password():
    password = request.form.get("password", "")
    if current_user.is_demo:
        flash("Demo accounts can't be changed.")
    elif len(password) < MIN_PASSWORD_LENGTH:
        flash(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")
    else:
        current_user.password_hash = generate_password_hash(password)
        # Any login links still sitting in an inbox stop working.
        current_user.login_version += 1
        db.session.commit()
        flash("Password saved.")
    return redirect(url_for("auth.account"))


@bp.post("/account/delete")
@login_required
def delete_account():
    if current_user.is_demo:
        flash("Demo accounts can't be changed.")
        return redirect(url_for("auth.account"))

    user_id = current_user.id
    logout_user()
    # The database removes their posts, comments, reactions, communities and circle with them.
    db.session.execute(db.delete(User).where(User.id == user_id))
    db.session.commit()
    flash("Your account and everything in it have been deleted.")
    return redirect(url_for("main.home"))
