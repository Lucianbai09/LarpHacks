import re
from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, limiter
from .demo import DEMO_EMAIL_DOMAIN, USERS as DEMO_USERNAMES
from .mail import send_link_email
from .models import TERMS_VERSION, User
from .security import MIN_PASSWORD_LENGTH, captcha_passed, password_problem

bp = Blueprint("auth", __name__)

USERNAME_PATTERN = re.compile(r"[a-z0-9_]{3,30}")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MAX_EMAIL_LENGTH = 254

CONFIRM_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
RESET_MAX_AGE_SECONDS = 60 * 60

FORM_LIMIT = "10 per minute"
EMAIL_LIMIT = "5 per minute;30 per day"

CAPTCHA_FAILED = "Please complete the captcha and try again."
BAD_LINK = "That link has expired or was already used."


def back(fallback):
    """The `next` path sent with a request, only ever a page on this site."""
    target = request.values.get("next", "")
    return target if re.fullmatch(r"/(?![/\\])[^\s\\]*", target) else fallback


def make_link(endpoint, salt, payload):
    # Built from APP_URL, not the request, because a request's Host header can be faked.
    token = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt).dumps(payload)
    return current_app.config["APP_URL"] + url_for(endpoint, token=token)


def read_link(token, salt, max_age):
    try:
        return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt).loads(token, max_age=max_age)
    except BadData:
        return None


def send_confirmation(user):
    link = make_link("auth.confirm_email", "confirm-email", {"user_id": user.id, "email": user.email})
    send_link_email(user.email, "Confirm your LarpHacks email", "Confirm your email to get the checkmark on your account:", link)


def form_username():
    return request.form.get("username", "").strip().lower()


def form_email():
    return request.form.get("email", "").strip().lower()


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit(FORM_LIMIT, methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    username = form_username()
    email = form_email()
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")

        if not USERNAME_PATTERN.fullmatch(username):
            error = "Usernames are 3-30 letters, numbers or underscores."
        elif username in DEMO_USERNAMES:
            error = "That username is taken."
        elif not EMAIL_PATTERN.fullmatch(email) or len(email) > MAX_EMAIL_LENGTH:
            error = "That doesn't look like an email address."
        elif email.endswith(f"@{DEMO_EMAIL_DOMAIN}"):
            error = "Please use a real email address."
        elif password_problem(password):
            error = password_problem(password)
        elif not request.form.get("terms"):
            error = "Please agree to the Terms and Privacy Policy to continue."
        elif not captcha_passed():
            error = CAPTCHA_FAILED
        elif db.session.scalar(db.select(User).filter_by(username=username)):
            error = "That username is taken."
        elif db.session.scalar(db.select(User).filter_by(email=email)):
            error = "That email already has an account."
        else:
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                terms_version=TERMS_VERSION,
            )
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                # Two submits at once, such as a double click. The database lets only one through.
                db.session.rollback()
                error = "That username or email already has an account."
            else:
                login_user(user, remember=True)
                send_confirmation(user)
                flash("You're in. Join what you're quitting to start your count, and check your email for a confirmation link.")
                return redirect(url_for("main.category_list"))

    page = render_template("register.html", username=username, email=email, min_password_length=MIN_PASSWORD_LENGTH, error=error)
    return page, 400 if error else 200


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(FORM_LIMIT, methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    identifier = request.form.get("identifier", "").strip().lower()
    error = None

    if request.method == "POST":
        user = db.session.scalar(db.select(User).where(or_(User.username == identifier, User.email == identifier)))
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
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


@bp.route("/confirm-email/<token>", methods=["GET", "POST"])
def confirm_email(token):
    link = read_link(token, "confirm-email", CONFIRM_MAX_AGE_SECONDS)
    user = db.session.get(User, link["user_id"]) if link else None
    if not user or user.email != link["email"]:
        flash(BAD_LINK)
        return redirect(url_for("main.home"))

    # Opening a link only shows a button, because mail scanners open links by themselves.
    if request.method == "GET":
        return render_template("confirm_email.html")

    if not user.email_verified_at:
        user.email_verified_at = datetime.now(timezone.utc)
        db.session.commit()
    flash("Your email is confirmed.")
    return redirect(url_for("main.home"))


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit(EMAIL_LIMIT, methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("auth.account"))

    error = None

    if request.method == "POST":
        if not captcha_passed():
            error = CAPTCHA_FAILED
        else:
            user = db.session.scalar(db.select(User).filter_by(email=form_email()))
            if user and not user.is_demo:
                link = make_link("auth.reset_password", "reset-password", {"user_id": user.id, "fingerprint": user.password_fingerprint})
                send_link_email(user.email, "Reset your LarpHacks password", "Use this link to choose a new password. It works once and expires in 1 hour:", link)
            # The same message either way, so this form can't reveal who has an account here.
            flash("If that email has an account, a reset link is on its way. Check your spam folder too.")
            return redirect(url_for("auth.forgot_password"))

    page = render_template("forgot_password.html", error=error)
    return page, 400 if error else 200


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit(FORM_LIMIT, methods=["POST"])
def reset_password(token):
    link = read_link(token, "reset-password", RESET_MAX_AGE_SECONDS)
    user = db.session.get(User, link["user_id"]) if link else None
    # The link holds a fingerprint of the old password, so it stops working once that changes.
    if not user or user.is_demo or user.password_fingerprint != link["fingerprint"]:
        flash(BAD_LINK)
        return redirect(url_for("auth.forgot_password"))

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        error = password_problem(password)
        if not error:
            user.password_hash = generate_password_hash(password)
            # They got here through their inbox, which proves the email is theirs.
            user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
            db.session.commit()
            login_user(user, remember=True)
            flash("Password saved.")
            return redirect(url_for("main.home"))

    page = render_template("reset_password.html", min_password_length=MIN_PASSWORD_LENGTH, error=error)
    return page, 400 if error else 200


@bp.route("/account")
@login_required
def account():
    return render_template("account.html", min_password_length=MIN_PASSWORD_LENGTH)


@bp.post("/account/confirm-email")
@login_required
@limiter.limit(EMAIL_LIMIT)
def resend_confirmation():
    if not current_user.is_demo and not current_user.email_verified_at:
        send_confirmation(current_user)
        flash("Confirmation link sent. Check your spam folder too.")
    return redirect(url_for("auth.account"))


@bp.post("/account/password")
@login_required
def set_password():
    password = request.form.get("password", "")
    if current_user.is_demo:
        flash("Demo accounts can't be changed.")
    elif password_problem(password):
        flash(password_problem(password))
    else:
        user = current_user._get_current_object()
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        # Changing the password logs out every device, so log this one back in.
        login_user(user, remember=True)
        flash("Password saved. Any other devices have been logged out.")
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
