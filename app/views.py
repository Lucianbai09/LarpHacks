from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from . import db
from .auth import back
from .models import (
    REPORT_TYPES,
    VISIBILITIES,
    Category,
    CircleLink,
    Comment,
    Membership,
    Post,
    Reaction,
    User,
    circle_link,
    circle_links,
    visible_to,
)

bp = Blueprint("main", __name__)

FEED_LIMIT = 50


def all_categories():
    return db.session.scalars(db.select(Category).order_by(Category.name)).all()


def get_category(slug):
    return db.first_or_404(db.select(Category).filter_by(slug=slug))


def get_visible_post(post_id):
    # A post you can't see is a 404, so its existence doesn't leak either.
    return db.first_or_404(db.select(Post).where(Post.id == post_id, visible_to(current_user)))


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


@bp.app_context_processor
def nav_counts():
    if not current_user.is_authenticated:
        return {"circle_requests": 0}
    query = db.select(func.count()).select_from(CircleLink).filter_by(addressee_id=current_user.id, accepted=False)
    return {"circle_requests": db.session.scalar(query)}


@bp.route("/")
def home():
    return render_template("home.html", categories=all_categories(), posts=feed())


@bp.route("/categories")
def category_list():
    return render_template("categories.html", categories=all_categories(), memberships=my_memberships())


@bp.route("/categories/<slug>")
def category_feed(slug):
    category = get_category(slug)
    return render_template(
        "category.html",
        category=category,
        membership=my_memberships().get(category.id),
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


@bp.route("/write", methods=["GET", "POST"])
@login_required
def write():
    # GET reads ?category=<slug> to preselect, POST reads the submitted form.
    form = request.form if request.method == "POST" else request.args
    error = None

    if request.method == "POST":
        body = form.get("body", "").strip()
        slug = form.get("category")
        report_type = form.get("report_type")
        visibility = form.get("visibility")
        category = db.session.scalar(db.select(Category).filter_by(slug=slug)) if slug else None

        if not body:
            error = "Write something first."
        elif report_type not in REPORT_TYPES or visibility not in VISIBILITIES or (slug and not category):
            error = "Pick a valid category, type and audience."
        else:
            db.session.add(
                Post(user_id=current_user.id, category=category, report_type=report_type, visibility=visibility, body=body)
            )
            db.session.commit()
            return redirect(url_for("main.category_feed", slug=slug) if slug else url_for("main.home"))

    page = render_template(
        "write.html",
        categories=all_categories(),
        report_types=REPORT_TYPES,
        visibilities=VISIBILITIES,
        form=form,
        error=error,
    )
    return page, 400 if error else 200


@bp.route("/posts/<int:post_id>")
def post_detail(post_id):
    return render_template("post.html", post=get_visible_post(post_id))


@bp.post("/posts/<int:post_id>/believe")
@login_required
def believe(post_id):
    post = get_visible_post(post_id)
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
    post = get_visible_post(post_id)
    body = request.form.get("body", "").strip()
    if body:
        db.session.add(Comment(post_id=post.id, user_id=current_user.id, body=body))
        db.session.commit()
    return redirect(url_for("main.post_detail", post_id=post.id))


@bp.route("/u/<username>")
def profile(username):
    user = db.first_or_404(db.select(User).filter_by(username=username))
    is_me = current_user == user
    link = circle_link(current_user, user) if current_user.is_authenticated and not is_me else None
    in_circle = link is not None and link.accepted

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
