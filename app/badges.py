from datetime import timedelta

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from . import db
from .models import CheckIn, EarnedBadge, Post, Reaction, circle_links

# These reward showing up and being honest, not only clean days. Tier is the medal's colour, from 1 to 5.
ACHIEVEMENTS = [
    {"id": "first", "icon": "check", "tier": 1, "name": "First step", "desc": "Did your first check-in."},
    {"id": "honest", "icon": "chat", "tier": 2, "name": "Honest day", "desc": "Logged a slip instead of skipping the day."},
    {"id": "comeback", "icon": "rebound", "tier": 3, "name": "Comeback", "desc": "Back in character the day after a slip."},
    {"id": "perfect", "icon": "star", "tier": 4, "name": "Perfect week", "desc": "In character seven check-ins in a row."},
    {"id": "fronts", "icon": "shield", "tier": 3, "name": "Many fronts", "desc": "Quitting more than one habit at once."},
    {"id": "open", "icon": "pen", "tier": 2, "name": "Open book", "desc": "Posted a photo or a reflection."},
    {"id": "cheer", "icon": "heart", "tier": 2, "name": "Cheerleader", "desc": "Believed someone else's post."},
    {"id": "partner", "icon": "people", "tier": 3, "name": "Partnered up", "desc": "Got someone into your circle."},
    {"id": "story", "icon": "share", "tier": 3, "name": "Storyteller", "desc": "Shared a post with a community."},
    {"id": "circle", "icon": "plus", "tier": 2, "name": "Circle of three", "desc": "Three people in your circle."},
]


def count_posts(user, *conditions):
    return db.session.scalar(db.select(func.count()).select_from(Post).where(Post.user_id == user.id, *conditions))


def qualifying_badges(user):
    entries = db.session.scalars(db.select(CheckIn).filter_by(user_id=user.id).order_by(CheckIn.day)).all()
    comeback = False
    run = best_run = 0
    previous = None
    for entry in entries:
        next_day = previous is not None and entry.day == previous.day + timedelta(days=1)
        comeback = comeback or (next_day and not previous.on_track and entry.on_track)
        run = (run + 1 if next_day else 1) if entry.on_track else 0
        best_run = max(best_run, run)
        previous = entry

    believed_others = db.session.scalar(
        db.select(func.count())
        .select_from(Reaction)
        .join(Post, Reaction.post_id == Post.id)
        .where(Reaction.user_id == user.id, Post.user_id != user.id)
    )
    friends = sum(link.accepted for link in circle_links(user))

    checks = {
        "first": bool(entries),
        "honest": any(not entry.on_track for entry in entries),
        "comeback": comeback,
        "perfect": best_run >= 7,
        "fronts": len(user.memberships) >= 2,
        "open": count_posts(user, or_(Post.report_type == "reflection", Post.photo.has())) > 0,
        "cheer": believed_others > 0,
        "partner": friends >= 1,
        "story": count_posts(user, Post.visibility == "public", Post.categories.any()) > 0,
        "circle": friends >= 3,
    }
    return {badge for badge, passed in checks.items() if passed}


def new_badges(user):
    """Adds any badges `user` has just qualified for, and returns them. The caller commits."""
    have = set(db.session.scalars(db.select(EarnedBadge.badge).filter_by(user_id=user.id)))
    qualifying = qualifying_badges(user)
    earned = [achievement for achievement in ACHIEVEMENTS if achievement["id"] in qualifying - have]
    db.session.add_all(EarnedBadge(user_id=user.id, badge=achievement["id"]) for achievement in earned)
    return earned


def award_badges(user):
    earned = new_badges(user)
    if earned:
        try:
            db.session.commit()
        except IntegrityError:
            # A double click got there first, and that request announces them.
            db.session.rollback()
            return []
    return earned


def badge_summary(user):
    earned_on = dict(db.session.execute(db.select(EarnedBadge.badge, EarnedBadge.earned_on).filter_by(user_id=user.id)).all())
    achievements = [{**achievement, "earned_on": earned_on.get(achievement["id"])} for achievement in ACHIEVEMENTS]
    earned = [achievement for achievement in achievements if achievement["earned_on"]]
    return {
        "achievements": achievements,
        "count": len(earned),
        "total": len(achievements),
        # Reversed, so on a tie it's the one further down the list, which is usually harder.
        "latest": max(reversed(earned), key=lambda achievement: achievement["earned_on"], default=None),
    }
