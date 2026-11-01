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
    ("scrolling", "Scrolling", "phone", "doomscroll"),
    ("vaping", "Vaping", "vape", "vape"),
    ("gaming", "Gaming", "gamepad", "game on autopilot"),
    ("alcohol", "Alcohol", "glass", "need a drink"),
    ("weed", "Weed", "leaf", "smoke weed"),
    ("gambling", "Betting", "dice", "bet"),
    ("energy-drinks", "Energy drinks", "bolt", "run on energy drinks"),
    ("shopping", "Impulse buying", "bag", "impulse buy"),
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

# The scale for "how are you feeling today?" on the daily check-in.
MOODS = range(1, 11)

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
    profile = db.relationship("Profile", uselist=False)

    @property
    def pledge(self):
        written = self.profile.pledge if self.profile else None
        return written or pledge_for(membership.category for membership in self.memberships)

    @property
    def pledge_shared(self):
        return self.profile.pledge_shared if self.profile else True

    @property
    def default_audience(self):
        return self.profile.audience if self.profile else None

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


class Profile(db.Model):
    """What someone chose in the setup steps. Without a row, they just get the defaults."""

    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # NULL means use the suggested pledge, which follows the communities they join.
    pledge = db.Column(db.String(200))
    # Their circle can already see what they're quitting, so that's who a shared pledge goes to.
    pledge_shared = db.Column(db.Boolean, nullable=False, default=True)
    audience = db.Column(db.String(20))


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

    @property
    def icon(self):
        return CATEGORY_LOOKS[self.slug][0]

    @property
    def pledge(self):
        return pledge_for([self])


def pledge_for(categories):
    """One sentence for everything someone is quitting: "I'm someone who doesn't doomscroll or vape." """
    verbs = [CATEGORY_LOOKS[category.slug][1] for category in categories]
    if not verbs:
        return "I'm someone who's already quit."
    joined = verbs[0] if len(verbs) == 1 else f"{', '.join(verbs[:-1])} or {verbs[-1]}"
    return f"I'm someone who doesn't {joined}."


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


# The communities a post went into. A post with none is Overall, and only shows in the overall feed.
post_category = db.Table(
    "post_category",
    db.Column("post_id", db.ForeignKey("post.id", ondelete="CASCADE"), primary_key=True),
    db.Column("category_id", db.ForeignKey("category.id"), primary_key=True),
)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    report_type = db.Column(db.String(20), nullable=False, default="post")
    visibility = db.Column(db.String(20), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    author = db.relationship(User, lazy="joined")
    categories = db.relationship(Category, secondary=post_category, lazy="selectin", order_by=Category.name)
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


# The communities someone stayed in character for on a check-in.
check_in_category = db.Table(
    "check_in_category",
    db.Column("user_id", db.Integer, primary_key=True),
    db.Column("day", db.Date, primary_key=True),
    db.Column("category_id", db.ForeignKey("category.id"), primary_key=True),
    db.ForeignKeyConstraint(["user_id", "day"], ["check_in.user_id", "check_in.day"], ondelete="CASCADE"),
)


class CheckIn(db.Model):
    """One person's answers for one day. Only they can see it, unless they share it, which makes a normal post."""

    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day = db.Column(db.Date, primary_key=True, default=date.today)
    mood = db.Column(db.Integer, nullable=False)
    # Whether they ticked every community they were in. Saved, because they can join or leave one later.
    on_track = db.Column(db.Boolean, nullable=False)
    post_id = db.Column(db.ForeignKey("post.id", ondelete="SET NULL"))

    post = db.relationship(Post)
    larped = db.relationship(Category, secondary=check_in_category, lazy="selectin", order_by=Category.name)

    @property
    def mood_label(self):
        return f"{self.mood}/10"

    @property
    def larped_label(self):
        return ", ".join(category.name for category in self.larped) or "Not today"

    @property
    def audience(self):
        return self.post.visibility if self.post else "private"

    @property
    def answers(self):
        """The answers as the form sends them, to fill it in again when editing."""
        return {"mood": str(self.mood), "visibility": self.audience}

    @property
    def summary(self):
        """The text of the post when this is shared. It only names what they ticked, so it can't out anything else."""
        parts = [f"Feeling {self.mood_label}."]
        if self.larped:
            parts.append(f"Stayed in character: {self.larped_label}.")
        elif not self.on_track:
            parts.append("Didn't stay in character today, and being honest about it.")
        return " ".join(parts)


class EarnedBadge(db.Model):
    """An achievement someone has earned. The list of them is in badges.py."""

    user_id = db.Column(db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    badge = db.Column(db.String(20), primary_key=True)
    earned_on = db.Column(db.Date, nullable=False, default=date.today)


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
