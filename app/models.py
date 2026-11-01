from datetime import date

from flask_login import UserMixin
from sqlalchemy import and_, or_
from sqlalchemy.sql import func

from . import db, login_manager

# Adding a habit: add a line here, then run `flask init-db`.
CATEGORIES = [
    ("alcohol", "Alcohol"),
    ("scrolling", "Scrolling"),
    ("gaming", "Gaming"),
]

REPORT_TYPES = {
    "post": "Post",
    "daily": "Daily report",
    "weekly": "Weekly report",
    "monthly": "Monthly report",
}

VISIBILITIES = {
    "public": "Community",
    "circle": "My circle",
    "private": "Only me",
}


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    memberships = db.relationship("Membership")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)


class Membership(db.Model):
    user_id = db.Column(db.ForeignKey("users.id"), primary_key=True)
    category_id = db.Column(db.ForeignKey("category.id"), primary_key=True)
    # The day the "days in character" count runs from.
    started_on = db.Column(db.Date, nullable=False, default=date.today)

    category = db.relationship(Category, lazy="joined")

    @property
    def days_label(self):
        days = (date.today() - self.started_on).days
        return f"{days} day{'' if days == 1 else 's'} in character"


class CircleLink(db.Model):
    requester_id = db.Column(db.ForeignKey("users.id"), primary_key=True)
    addressee_id = db.Column(db.ForeignKey("users.id"), primary_key=True)
    accepted = db.Column(db.Boolean, nullable=False, default=False)

    requester = db.relationship(User, foreign_keys=[requester_id], lazy="joined")
    addressee = db.relationship(User, foreign_keys=[addressee_id], lazy="joined")

    def other(self, user):
        return self.addressee if self.requester_id == user.id else self.requester


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    # NULL means the post only shows in the overall feed.
    category_id = db.Column(db.ForeignKey("category.id"))
    report_type = db.Column(db.String(20), nullable=False, default="post")
    visibility = db.Column(db.String(20), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    author = db.relationship(User, lazy="joined")
    category = db.relationship(Category, lazy="joined")
    comments = db.relationship("Comment", back_populates="post", lazy="selectin", order_by="Comment.id")
    reactions = db.relationship("Reaction", lazy="selectin")

    @property
    def report_label(self):
        return REPORT_TYPES[self.report_type]

    @property
    def visibility_label(self):
        return VISIBILITIES[self.visibility]

    def believed_by(self, user):
        return user.is_authenticated and any(r.user_id == user.id for r in self.reactions)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    author = db.relationship(User, lazy="joined")
    post = db.relationship(Post, back_populates="comments")


class Reaction(db.Model):
    """An "I believe you" on a post."""

    user_id = db.Column(db.ForeignKey("users.id"), primary_key=True)
    post_id = db.Column(db.ForeignKey("post.id"), primary_key=True)


def circle_links(user):
    query = db.select(CircleLink).where(or_(CircleLink.requester_id == user.id, CircleLink.addressee_id == user.id))
    return db.session.scalars(query).all()


def circle_link(user, other):
    return next((link for link in circle_links(user) if link.other(user).id == other.id), None)


def visible_to(user):
    """SQL filter for the posts `user` may see. Every query that reads posts must use it."""
    if not user.is_authenticated:
        return Post.visibility == "public"
    friend_ids = [link.other(user).id for link in circle_links(user) if link.accepted]
    return or_(
        Post.visibility == "public",
        Post.user_id == user.id,
        and_(Post.visibility == "circle", Post.user_id.in_(friend_ids)),
    )


def init_db():
    db.create_all()
    for slug, name in CATEGORIES:
        if not db.session.scalar(db.select(Category).filter_by(slug=slug)):
            db.session.add(Category(slug=slug, name=name))
    db.session.commit()
