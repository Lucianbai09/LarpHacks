import hashlib
from datetime import date

from flask_login import UserMixin
from sqlalchemy import and_, or_
from sqlalchemy.orm import deferred
from sqlalchemy.sql import func

from . import db, login_manager

# Adding a habit: add a line here, then run `flask init-db`.
# Slug, name, an icon from _icons.html, and the end of "I'm someone who doesn't ...".
CATEGORIES = [
    ("alcohol", "Alcohol", "glass", "need a drink"),
    ("scrolling", "Scrolling", "phone", "doomscroll"),
    ("gaming", "Gaming", "gamepad", "game on autopilot"),
]
CATEGORY_LOOKS = {slug: (icon, verb) for slug, _, icon, verb in CATEGORIES}

# Days in character for each medal, and what it's called.
MILESTONES = [(1, "1 day"), (7, "1 week"), (14, "2 weeks"), (30, "1 month"), (90, "3 months")]

# What people can choose on the Write page.
WRITE_TYPES = {
    "post": "Post",
    "daily": "Daily report",
    "weekly": "Weekly report",
    "monthly": "Monthly report",
    "reflection": "Reflection",
}

# A shared daily check-in becomes a post of its own type.
REPORT_TYPES = {**WRITE_TYPES, "checkin": "Check-in"}

# The answers on the daily check-in.
MOODS = {1: "Awful", 2: "Low", 3: "Okay", 4: "Good", 5: "Great"}
URGES = {0: "None", 1: "Mild", 2: "Some", 3: "Strong", 4: "Intense"}
TRIGGERS = {
    "stress": "Stress",
    "boredom": "Boredom",
    "people": "Other people",
    "tired": "Being tired",
    "nothing": "Nothing today",
}

VISIBILITIES = {
    "public": "Community",
    "circle": "My circle",
    "private": "Only me",
}

# Change this when the Terms or Privacy Policy change.
TERMS_VERSION = "2026-11-01"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email_verified_at = db.Column(db.DateTime(timezone=True))
    # Only `flask seed-demo` sets this. Demo passwords are public, so these accounts are walled off from real ones.
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    terms_version = db.Column(db.String(20), nullable=False)
    terms_accepted_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    memberships = db.relationship("Membership")

    @property
    def password_fingerprint(self):
        return hashlib.sha256(self.password_hash.encode()).hexdigest()[:16]

    def get_id(self):
        # Includes the password, so changing it logs out every other device.
        return f"{self.id}:{self.password_fingerprint}"

    def can_link_with(self, other):
        # A demo account in a real circle would let anyone read that circle's posts.
        return self.is_demo == other.is_demo


@login_manager.user_loader
def load_user(session_id):
    user_id, _, fingerprint = session_id.partition(":")
    user = db.session.get(User, int(user_id))
    return user if user and user.password_fingerprint == fingerprint else None


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

    @property
    def icon(self):
        return CATEGORY_LOOKS[self.slug][0]

    @property
    def pledge(self):
        return f"I'm someone who doesn't {CATEGORY_LOOKS[self.slug][1]}."


class Membership(db.Model):
    milestones = MILESTONES

    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    category_id = db.Column(db.ForeignKey("category.id"), primary_key=True)
    # The day the "days in character" count runs from.
    started_on = db.Column(db.Date, nullable=False, default=date.today)

    category = db.relationship(Category, lazy="joined")

    @property
    def days(self):
        return (date.today() - self.started_on).days

    @property
    def days_label(self):
        return f"{self.days} day{'' if self.days == 1 else 's'} in character"

    @property
    def next_milestone(self):
        return next((milestone for milestone in MILESTONES if milestone[0] > self.days), None)


class CircleLink(db.Model):
    requester_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    addressee_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    accepted = db.Column(db.Boolean, nullable=False, default=False)

    requester = db.relationship(User, foreign_keys=[requester_id], lazy="joined")
    addressee = db.relationship(User, foreign_keys=[addressee_id], lazy="joined")

    def other(self, user):
        return self.addressee if self.requester_id == user.id else self.requester


class PostPhoto(db.Model):
    """A post's picture. It lives in the database because Render's free plan has no lasting disk."""

    post_id = db.Column(db.ForeignKey("post.id", ondelete="CASCADE"), primary_key=True)
    # Deferred, so feeds can tell a post has a photo without loading the photo itself.
    data = deferred(db.Column(db.LargeBinary, nullable=False))


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
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
    photo = db.relationship(PostPhoto, lazy="selectin", uselist=False)

    @property
    def report_label(self):
        return REPORT_TYPES[self.report_type]

    @property
    def visibility_label(self):
        return VISIBILITIES[self.visibility]

    def believed_by(self, user):
        return user.is_authenticated and any(r.user_id == user.id for r in self.reactions)

    def open_to(self, user):
        # Demo passwords are public, so those accounts can't write on real people's posts.
        return not user.is_demo or self.author.is_demo


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.ForeignKey("post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    author = db.relationship(User, lazy="joined")
    post = db.relationship(Post, back_populates="comments")


class Reaction(db.Model):
    """An "I believe you" on a post."""

    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    post_id = db.Column(db.ForeignKey("post.id", ondelete="CASCADE"), primary_key=True)


class CheckIn(db.Model):
    """One person's answers for one day. Only they can see it, unless they share it, which makes a normal post."""

    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day = db.Column(db.Date, primary_key=True, default=date.today)
    mood = db.Column(db.Integer, nullable=False)
    urges = db.Column(db.Integer, nullable=False)
    on_track = db.Column(db.Boolean, nullable=False)
    trigger = db.Column(db.String(20))
    post_id = db.Column(db.ForeignKey("post.id", ondelete="SET NULL"))

    post = db.relationship(Post)

    @property
    def mood_label(self):
        return MOODS[self.mood]

    @property
    def urges_label(self):
        return URGES[self.urges]

    @property
    def trigger_label(self):
        return TRIGGERS.get(self.trigger)

    @property
    def audience(self):
        return self.post.visibility if self.post else "private"

    @property
    def answers(self):
        """The answers as the form sends them, to fill it in again when editing."""
        return {
            "mood": str(self.mood),
            "urges": str(self.urges),
            "on_track": "yes" if self.on_track else "no",
            "trigger": self.trigger or "",
            "visibility": self.audience,
        }

    @property
    def summary(self):
        """The text of the post when this is shared."""
        parts = [f"Feeling {self.mood_label.lower()}.", f"Urges: {self.urges_label.lower()}."]
        if self.trigger and self.trigger != "nothing":
            parts.append(f"Hardest part: {self.trigger_label.lower()}.")
        parts.append("Stayed in character." if self.on_track else "Slipped today, and being honest about it.")
        return " ".join(parts)


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
    for slug, name, _, _ in CATEGORIES:
        if not db.session.scalar(db.select(Category).filter_by(slug=slug)):
            db.session.add(Category(slug=slug, name=name))
    db.session.commit()
