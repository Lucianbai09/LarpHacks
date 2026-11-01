from collections import Counter
from datetime import date, timedelta
from statistics import mean

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from . import db, limiter
from .auth import back
from .badges import award_badges, badge_summary
from .models import (
    MOODS,
    TERMS_VERSION,
    VISIBILITIES,
    WRITE_TYPES,
    Category,
    CheckIn,
    CircleLink,
    Comment,
    Membership,
    Post,
    PostPhoto,
    Profile,
    Reaction,
    User,
    circle_link,
    circle_links,
    pledge_for,
    visible_to,
)
from .photos import MAX_PHOTO_MB, clean_photo

bp = Blueprint("main", __name__)

FEED_LIMIT = 50
MAX_POST_LENGTH = 5000
MAX_COMMENT_LENGTH = 2000
MAX_PLEDGE_LENGTH = 200
SETUP_STEPS = 3
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


def my_categories():
    memberships = my_memberships()
    return [category for category in all_categories() if category.id in memberships]


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


def check_in_streak():
    """Days in a row you've checked in, honest slips included, counting from today or yesterday."""
    days = db.session.scalars(
        db.select(CheckIn.day).where(CheckIn.user_id == current_user.id).order_by(CheckIn.day.desc()).limit(400)
    ).all()
    expected = date.today() if days and days[0] == date.today() else date.today() - timedelta(days=1)
    streak = 0
    for day in days:
        if day != expected:
            break
        streak += 1
        expected -= timedelta(days=1)
    return streak


def logged_entries(week):
    return [item["entry"] for item in week if item["entry"]]


def summarize(entries):
    if not entries:
        return None
    return {
        "count": len(entries),
        "on_track": sum(entry.on_track for entry in entries),
        "mood": round(mean(entry.mood for entry in entries)),
        "larped": Counter(category.slug for entry in entries for category in entry.larped),
    }


@bp.app_context_processor
def nav_counts():
    if not current_user.is_authenticated:
        return {"circle_requests": 0, "checked_in_today": False}
    query = db.select(func.count()).select_from(CircleLink).filter_by(addressee_id=current_user.id, accepted=False)
    return {"circle_requests": db.session.scalar(query), "checked_in_today": todays_check_in() is not None}


@bp.after_request
def announce_new_badges(response):
    # Everything that can earn a badge is a POST in this file, so this is the one place to check.
    if request.method == "POST" and current_user.is_authenticated and response.status_code < 400:
        for badge in award_badges(current_user):
            # The whole badge, so the banner can show its medal.
            flash(badge, "badge")
    return response


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
            streak=check_in_streak(),
            badges=badge_summary(current_user),
            posts=feed(),
        )
    # Check-in one-liners and photo-only posts make dull stories around the campfire.
    return render_template("landing.html", posts=feed(Post.report_type != "checkin", Post.body != ""))


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
        posts=feed(Post.categories.any()),
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
        posts=feed(Post.categories.any(id=category.id)),
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
    category = get_category(slug)
    membership = my_memberships().get(category.id)
    if membership:
        membership.started_on = date.today()
        # Otherwise a tick from earlier today would still count as a day.
        entry = todays_check_in()
        if entry and category in entry.larped:
            entry.larped.remove(category)
            entry.on_track = False
        db.session.commit()
    return redirect(back(url_for("main.category_feed", slug=slug)))


def chosen_categories(form):
    """The communities ticked on a form, where no ticks means Overall. None if the choice isn't valid."""
    slugs = form.getlist("category")
    wanted = {slug for slug in slugs if slug}
    # Overall's own box sends an empty value, and it can't go with anything else.
    if wanted and "" in slugs:
        return None
    categories = db.session.scalars(db.select(Category).where(Category.slug.in_(wanted))).all()
    return categories if len(categories) == len(wanted) else None


def larped_categories(form):
    """The communities ticked on a check-in. None if any of them isn't one you're in."""
    ticked = set(form.getlist("larped"))
    larped = [category for category in my_categories() if category.slug in ticked]
    return larped if len(larped) == len(ticked) else None


def share_check_in(entry, visibility):
    # Sharing makes a normal post, so visible_to() and the feeds cover it.
    if visibility == "private":
        if entry.post:
            post_id = entry.post_id
            entry.post = None
            db.session.flush()
            db.session.execute(db.delete(Post).where(Post.id == post_id))
    elif entry.post:
        entry.post.visibility = visibility
        entry.post.body = entry.summary
        entry.post.categories = list(entry.larped)
    else:
        entry.post = Post(
            user_id=current_user.id,
            report_type="checkin",
            visibility=visibility,
            body=entry.summary,
            categories=list(entry.larped),
        )


@bp.route("/check-in", methods=["GET", "POST"])
@login_required
def check_in():
    entry = todays_check_in()
    error = None

    if request.method == "POST":
        mood = request.form.get("mood", type=int)
        visibility = request.form.get("visibility")
        larped = larped_categories(request.form)

        if mood not in MOODS or visibility not in VISIBILITIES or larped is None:
            error = "Pick how you're feeling from 1 to 10 to save."
        else:
            entry = entry or CheckIn(user_id=current_user.id, day=date.today())
            entry.mood, entry.larped = mood, larped
            entry.on_track = len(larped) == len(current_user.memberships)
            db.session.add(entry)
            share_check_in(entry, visibility)
            try:
                db.session.commit()
            except IntegrityError:
                # A double click. The first one already saved it.
                db.session.rollback()
            return redirect(url_for("main.check_in"))

    if entry and not error and "edit" not in request.args:
        missed = [membership for membership in current_user.memberships if membership.category not in entry.larped]
        return render_template(
            "check_in_done.html", entry=entry, visibilities=VISIBILITIES, missed=missed, streak=check_in_streak()
        )

    if request.method == "POST":
        ticked = request.form.getlist("larped")
    else:
        ticked = [category.slug for category in entry.larped] if entry else []

    page = render_template(
        "check_in.html",
        entry=entry,
        answers=request.form if request.method == "POST" else (entry.answers if entry else {}),
        ticked=ticked,
        categories=my_categories(),
        moods=MOODS,
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
    # Lowest mood, and a slip breaks a tie.
    hardest = min(entries, key=lambda entry: (entry.mood, entry.on_track)) if len(entries) > 1 else None
    report = None
    if summary:
        report = (
            f"This week: {summary['on_track']} of {summary['count']} days in character. "
            f"Feeling about {summary['mood']}/10."
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
        report_type = form.get("report_type")
        visibility = form.get("visibility")
        categories = chosen_categories(form)
        upload = request.files.get("photo")
        picked_photo = upload is not None and upload.filename != ""
        photo = clean_photo(upload.stream) if picked_photo else None

        if picked_photo and not photo:
            error = "That photo couldn't be read. Try a JPG or PNG."
        elif not body and not photo:
            error = "Write something or add a photo first."
        elif len(body) > MAX_POST_LENGTH:
            error = f"Posts can be up to {MAX_POST_LENGTH} characters."
        elif report_type not in WRITE_TYPES or visibility not in VISIBILITIES or categories is None:
            error = "Pick valid communities, a type and an audience."
        else:
            db.session.add(
                Post(
                    user_id=current_user.id,
                    categories=categories,
                    report_type=report_type,
                    visibility=visibility,
                    body=body,
                    photo=PostPhoto(data=photo) if photo else None,
                )
            )
            db.session.commit()
            # One community has its own feed to land on. Several only meet on the home feed.
            if len(categories) == 1:
                return redirect(url_for("main.category_feed", slug=categories[0].slug))
            return redirect(url_for("main.home"))

    page = render_template(
        "write.html",
        categories=all_categories(),
        chosen=form.getlist("category"),
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
    # The page's script asks for this instead of a redirect, so pressing the button never moves the page.
    if request.headers.get("X-Requested-With") == "fetch":
        return {"believed": not reaction, "believers": len(post.reactions), "badges": [badge["name"] for badge in award_badges(current_user)]}
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
        pledge=user.pledge if is_me or (in_circle and user.pledge_shared) else None,
        editing_pledge=is_me and request.args.get("edit") == "pledge",
        max_pledge_length=MAX_PLEDGE_LENGTH,
        badges=badge_summary(user) if is_me else None,
    )


def save_pledge(wording, shared):
    """Returns what's wrong with it, if anything. The caller commits."""
    wording = wording.strip()
    if len(wording) > MAX_PLEDGE_LENGTH:
        return f"Pledges can be up to {MAX_PLEDGE_LENGTH} characters."
    suggested = pledge_for(membership.category for membership in current_user.memberships)
    profile = current_user.profile or Profile(user_id=current_user.id)
    # Left as suggested, it keeps following the communities they join.
    profile.pledge = None if wording == suggested else wording or None
    profile.pledge_shared = shared
    db.session.add(profile)
    return None


@bp.post("/pledge")
@login_required
def pledge():
    error = save_pledge(request.form.get("pledge", ""), "shared" in request.form)
    if error:
        flash(error)
    else:
        db.session.commit()
        flash("Pledge saved.")
    return redirect(url_for("main.profile", username=current_user.username, _anchor="pledge"))


def join_only(categories):
    """Makes someone's communities exactly these, keeping the counts of the ones they stay in."""
    keep = {category.id for category in categories}
    have = my_memberships()
    for membership in have.values():
        if membership.category_id not in keep:
            db.session.delete(membership)
    for category in categories:
        if category.id not in have:
            db.session.add(Membership(user_id=current_user.id, category_id=category.id))


@bp.route("/setup/<int:step>", methods=["GET", "POST"])
@login_required
def setup(step):
    if not 1 <= step <= SETUP_STEPS:
        abort(404)
    form = request.form
    error = None

    if request.method == "POST":
        if step == 1:
            slugs = set(form.getlist("habit"))
            categories = db.session.scalars(db.select(Category).where(Category.slug.in_(slugs))).all()
            if not categories or len(categories) != len(slugs):
                error = "Choose at least one to continue."
            else:
                join_only(categories)
        elif step == 2:
            error = save_pledge(form.get("pledge", ""), "shared" in form)
        elif form.get("visibility") not in VISIBILITIES:
            error = "Choose who can see your progress."
        else:
            profile = current_user.profile or Profile(user_id=current_user.id)
            profile.audience = form["visibility"]
            db.session.add(profile)

        if not error:
            db.session.commit()
            if step < SETUP_STEPS:
                return redirect(url_for("main.setup", step=step + 1))
            flash("You're all set. Your first check-in is ready.")
            return redirect(url_for("main.home"))

    page = render_template(
        "setup.html",
        step=step,
        total=SETUP_STEPS,
        categories=all_categories(),
        joined=[membership.category.slug for membership in current_user.memberships],
        ticked=form.getlist("habit") if request.method == "POST" else None,
        pledge_text=form.get("pledge", current_user.pledge),
        pledge_shared="shared" in form if request.method == "POST" else current_user.pledge_shared,
        max_pledge_length=MAX_PLEDGE_LENGTH,
        visibilities=VISIBILITIES,
        error=error,
    )
    return page, 400 if error else 200


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
