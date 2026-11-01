from collections import Counter
from datetime import date, timedelta
from statistics import mean

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from . import db, limiter
from .auth import back
from .models import (
    MOODS,
    TERMS_VERSION,
    TRIGGERS,
    URGES,
    VISIBILITIES,
    WRITE_TYPES,
    Category,
    CheckIn,
    CircleLink,
    Comment,
    Membership,
    Post,
    PostPhoto,
    Reaction,
    User,
    circle_link,
    circle_links,
    visible_to,
)
from .photos import MAX_PHOTO_MB, clean_photo

bp = Blueprint("main", __name__)

FEED_LIMIT = 50
MAX_POST_LENGTH = 5000
MAX_COMMENT_LENGTH = 2000
# Photos are stored in a small free database, so this is stricter than the default.
WRITE_LIMIT = "20 per minute;200 per day"


def all_categories():
    return db.session.scalars(db.select(Category).order_by(Category.name)).all()


def get_category(slug):
    return db.first_or_404(db.select(Category).filter_by(slug=slug))


def get_visible_post(post_id):
    # A post you can't see is a 404, so its existence doesn't leak either.
    return db.first_or_404(db.select(Post).where(Post.id == post_id, visible_to(current_user)))


def get_writable_post(post_id):
    post = get_visible_post(post_id)
    if not post.open_to(current_user):
        abort(403)
    return post


def my_memberships():
    if not current_user.is_authenticated:
        return {}
    return {membership.category_id: membership for membership in current_user.memberships}


def feed(*filters):
    query = (
        db.select(Post)
        .where(visible_to(current_user), *filters)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(FEED_LIMIT)
    )
    return db.session.scalars(query).all()


def todays_check_in():
    return db.session.get(CheckIn, (current_user.id, date.today()))


def last_seven_days():
    """Each of the last seven days, oldest first, with your check-in if you did one."""
    today = date.today()
    query = db.select(CheckIn).where(CheckIn.user_id == current_user.id, CheckIn.day > today - timedelta(days=7))
    entries = {entry.day: entry for entry in db.session.scalars(query)}
    days = [today - timedelta(days=ago) for ago in range(6, -1, -1)]
    return [{"day": day, "entry": entries.get(day)} for day in days]


def logged_entries(week):
    return [item["entry"] for item in week if item["entry"]]


def summarize(entries):
    if not entries:
        return None
    triggers = Counter(entry.trigger for entry in entries if entry.trigger and entry.trigger != "nothing")
    return {
        "count": len(entries),
        "on_track": sum(entry.on_track for entry in entries),
        "mood": MOODS[round(mean(entry.mood for entry in entries))],
        "urges": URGES[round(mean(entry.urges for entry in entries))],
        "trigger": TRIGGERS[triggers.most_common(1)[0][0]] if triggers else None,
    }


@bp.app_context_processor
def nav_counts():
    if not current_user.is_authenticated:
        return {"circle_requests": 0, "checked_in_today": False}
    query = db.select(func.count()).select_from(CircleLink).filter_by(addressee_id=current_user.id, accepted=False)
    return {"circle_requests": db.session.scalar(query), "checked_in_today": todays_check_in() is not None}


@bp.route("/")
def home():
    if current_user.is_authenticated:
        week = last_seven_days()
        return render_template(
            "home.html",
            today=date.today(),
            week=week,
            week_summary=summarize(logged_entries(week)),
            check_in=todays_check_in(),
            posts=feed(),
        )
    return render_template("landing.html", posts=feed())


@bp.route("/terms")
def terms():
    return render_template("terms.html", terms_version=TERMS_VERSION)


@bp.route("/privacy")
def privacy():
    return render_template("privacy.html", terms_version=TERMS_VERSION)


@bp.route("/categories")
def category_list():
    return render_template(
        "categories.html",
        categories=all_categories(),
        memberships=my_memberships(),
        posts=feed(Post.category_id.is_not(None)),
    )


@bp.route("/categories/<slug>")
def category_feed(slug):
    category = get_category(slug)
    memberships = my_memberships()
    return render_template(
        "category.html",
        category=category,
        categories=all_categories(),
        memberships=memberships,
        membership=memberships.get(category.id),
        posts=feed(Post.category_id == category.id),
    )


@bp.post("/categories/<slug>/join")
@login_required
def join(slug):
    category = get_category(slug)
    if category.id not in my_memberships():
        db.session.add(Membership(user_id=current_user.id, category_id=category.id))
        db.session.commit()
    return redirect(back(url_for("main.category_feed", slug=slug)))


@bp.post("/categories/<slug>/leave")
@login_required
def leave(slug):
    membership = my_memberships().get(get_category(slug).id)
    if membership:
        db.session.delete(membership)
        db.session.commit()
    return redirect(back(url_for("main.category_feed", slug=slug)))


@bp.post("/categories/<slug>/restart")
@login_required
def restart(slug):
    membership = my_memberships().get(get_category(slug).id)
    if membership:
        membership.started_on = date.today()
        db.session.commit()
    return redirect(back(url_for("main.category_feed", slug=slug)))


def share_check_in(entry, visibility):
    # Sharing makes a normal post, so visible_to() and the feeds cover it. It's always Overall,
    # because an automatic post shouldn't reveal what someone is quitting.
    if visibility == "private":
        if entry.post:
            post_id = entry.post_id
            entry.post = None
            db.session.flush()
            db.session.execute(db.delete(Post).where(Post.id == post_id))
    elif entry.post:
        entry.post.visibility = visibility
        entry.post.body = entry.summary
    else:
        entry.post = Post(user_id=current_user.id, report_type="checkin", visibility=visibility, body=entry.summary)


@bp.route("/check-in", methods=["GET", "POST"])
@login_required
def check_in():
    entry = todays_check_in()
    error = None

    if request.method == "POST":
        mood = request.form.get("mood", type=int)
        urges = request.form.get("urges", type=int)
        on_track = request.form.get("on_track")
        trigger = request.form.get("trigger") or None
        visibility = request.form.get("visibility")

        if (
            mood not in MOODS
            or urges not in URGES
            or on_track not in ("yes", "no")
            or (trigger and trigger not in TRIGGERS)
            or visibility not in VISIBILITIES
        ):
            error = "Please answer questions 1 to 3 to save."
        else:
            entry = entry or CheckIn(user_id=current_user.id, day=date.today())
            entry.mood, entry.urges, entry.trigger = mood, urges, trigger
            entry.on_track = on_track == "yes"
            db.session.add(entry)
            share_check_in(entry, visibility)
            try:
                db.session.commit()
            except IntegrityError:
                # A double click. The first one already saved it.
                db.session.rollback()
            return redirect(url_for("main.check_in"))

    if entry and not error and "edit" not in request.args:
        return render_template(
            "check_in_done.html", entry=entry, visibilities=VISIBILITIES, memberships=current_user.memberships
        )

    page = render_template(
        "check_in.html",
        entry=entry,
        answers=request.form if request.method == "POST" else (entry.answers if entry else {}),
        moods=MOODS,
        urges=URGES,
        triggers=TRIGGERS,
        visibilities=VISIBILITIES,
        error=error,
    )
    return page, 400 if error else 200


@bp.route("/progress")
@login_required
def progress():
    week = last_seven_days()
    entries = logged_entries(week)
    summary = summarize(entries)
    # Lowest mood, and a slip or stronger urges break a tie.
    hardest = min(entries, key=lambda entry: (entry.mood, entry.on_track, -entry.urges)) if len(entries) > 1 else None
    report = None
    if summary:
        report = (
            f"This week: {summary['on_track']} of {summary['count']} days in character. "
            f"Mostly feeling {summary['mood'].lower()}."
        )

    query = db.select(CheckIn).where(CheckIn.user_id == current_user.id, CheckIn.day > date.today() - timedelta(days=30))
    return render_template(
        "progress.html",
        today=date.today(),
        week=week,
        summary=summary,
        hardest=hardest,
        report=report,
        month=summarize(db.session.scalars(query).all()),
    )


@bp.route("/write", methods=["GET", "POST"])
@login_required
@limiter.limit(WRITE_LIMIT, methods=["POST"])
def write():
    # GET reads ?category=<slug> and friends to preselect, POST reads the submitted form.
    form = request.form if request.method == "POST" else request.args
    error = None

    if request.method == "POST":
        body = form.get("body", "").strip()
        slug = form.get("category")
        report_type = form.get("report_type")
        visibility = form.get("visibility")
        category = db.session.scalar(db.select(Category).filter_by(slug=slug)) if slug else None
        upload = request.files.get("photo")
        picked_photo = upload is not None and upload.filename != ""
        photo = clean_photo(upload.stream) if picked_photo else None

        if picked_photo and not photo:
            error = "That photo couldn't be read. Try a JPG or PNG."
        elif not body and not photo:
            error = "Write something or add a photo first."
        elif len(body) > MAX_POST_LENGTH:
            error = f"Posts can be up to {MAX_POST_LENGTH} characters."
        elif report_type not in WRITE_TYPES or visibility not in VISIBILITIES or (slug and not category):
            error = "Pick a valid category, type and audience."
        else:
            db.session.add(
                Post(
                    user_id=current_user.id,
                    category=category,
                    report_type=report_type,
                    visibility=visibility,
                    body=body,
                    photo=PostPhoto(data=photo) if photo else None,
                )
            )
            db.session.commit()
            return redirect(url_for("main.category_feed", slug=slug) if slug else url_for("main.home"))

    page = render_template(
        "write.html",
        categories=all_categories(),
        report_types=WRITE_TYPES,
        visibilities=VISIBILITIES,
        max_length=MAX_POST_LENGTH,
        max_photo_mb=MAX_PHOTO_MB,
        form=form,
        error=error,
    )
    return page, 400 if error else 200


@bp.route("/posts/<int:post_id>")
def post_detail(post_id):
    return render_template("post.html", post=get_visible_post(post_id), max_length=MAX_COMMENT_LENGTH)


@bp.route("/posts/<int:post_id>/photo")
def post_photo(post_id):
    post = get_visible_post(post_id)
    if not post.photo:
        abort(404)
    response = make_response(post.photo.data)
    response.headers["Content-Type"] = "image/jpeg"
    # Asks the server every time, so being removed from a circle closes the photo as well.
    response.headers["Cache-Control"] = "private, no-cache"
    return response


@bp.post("/posts/<int:post_id>/believe")
@login_required
def believe(post_id):
    post = get_writable_post(post_id)
    reaction = db.session.get(Reaction, (current_user.id, post.id))
    if reaction:
        db.session.delete(reaction)
    else:
        db.session.add(Reaction(user_id=current_user.id, post_id=post.id))
    db.session.commit()
    return redirect(f"{back(url_for('main.home'))}#post-{post.id}")


@bp.post("/posts/<int:post_id>/comment")
@login_required
def comment(post_id):
    post = get_writable_post(post_id)
    body = request.form.get("body", "").strip()
    if len(body) > MAX_COMMENT_LENGTH:
        flash(f"Comments can be up to {MAX_COMMENT_LENGTH} characters.")
    elif body:
        db.session.add(Comment(post_id=post.id, user_id=current_user.id, body=body))
        db.session.commit()
    return redirect(url_for("main.post_detail", post_id=post.id))


@bp.route("/u/<username>")
def profile(username):
    user = db.first_or_404(db.select(User).filter_by(username=username))
    is_me = current_user == user
    link = circle_link(current_user, user) if current_user.is_authenticated and not is_me else None
    in_circle = link is not None and link.accepted
    can_link = current_user.is_authenticated and not is_me and current_user.can_link_with(user)

    comments = []
    believed = []
    if is_me:
        # Only interactions on posts you can still see, so leaving a circle closes them too.
        query = (
            db.select(Comment)
            .join(Comment.post)
            .where(Comment.user_id == user.id, visible_to(current_user))
            .order_by(Comment.id.desc())
            .limit(FEED_LIMIT)
        )
        comments = db.session.scalars(query).all()
        believed = feed(Post.reactions.any(user_id=user.id))

    return render_template(
        "profile.html",
        user=user,
        is_me=is_me,
        link=link,
        can_link=can_link,
        # What someone is quitting is sensitive, so strangers don't get to see it.
        memberships=user.memberships if is_me or in_circle else [],
        posts=feed(Post.user_id == user.id),
        comments=comments,
        believed=believed,
    )


@bp.route("/circle")
@login_required
def circle():
    links = circle_links(current_user)
    members = [link.other(current_user) for link in links if link.accepted]
    pending = [link for link in links if not link.accepted]
    return render_template(
        "circle.html",
        members=members,
        incoming=[link.requester for link in pending if link.addressee_id == current_user.id],
        outgoing=[link.addressee for link in pending if link.requester_id == current_user.id],
        posts=feed(Post.user_id.in_([member.id for member in members])),
    )


def find_user_from_form():
    username = request.form.get("username", "").strip().lower()
    return db.session.scalar(db.select(User).filter_by(username=username))


@bp.post("/circle/add")
@login_required
def circle_add():
    other = find_user_from_form()
    if not other or other == current_user:
        flash("No one else goes by that username.")
    elif not current_user.can_link_with(other):
        flash("Demo accounts and real accounts can't be in the same circle.")
    else:
        link = circle_link(current_user, other)
        if not link:
            db.session.add(CircleLink(requester_id=current_user.id, addressee_id=other.id))
            flash(f"Request sent to {other.username}.")
        elif link.addressee_id == current_user.id and not link.accepted:
            # They already asked, so asking back is accepting.
            link.accepted = True
            flash(f"{other.username} is in your circle.")
        db.session.commit()
    return redirect(back(url_for("main.circle")))


@bp.post("/circle/remove")
@login_required
def circle_remove():
    # Covers removing a member, declining a request and cancelling your own.
    other = find_user_from_form()
    link = circle_link(current_user, other) if other else None
    if link:
        db.session.delete(link)
        db.session.commit()
    return redirect(back(url_for("main.circle")))
