from datetime import date, datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from . import db
from .models import TERMS_VERSION, Category, CircleLink, Comment, Membership, Post, Reaction, User

PASSWORD = "larping123"

# Username, then each community they're in and their days in character.
USERS = {
    "maya": {"alcohol": 12},
    "theo": {"gaming": 50, "scrolling": 4},
    "sam": {"scrolling": 2},
}

# Maya and Theo are a circle. Sam has asked to join Maya's and is still waiting.
CIRCLE_LINKS = [
    ("maya", "theo", True),
    ("sam", "maya", False),
]

POSTS = [
    {
        "author": "theo",
        "category": "gaming",
        "report_type": "monthly",
        "visibility": "public",
        "days_ago": 20,
        "body": "One month without ranked. I told people I was the kind of person who goes to bed at eleven, and now I kind of am.",
        "comments": [("maya", "Going to bed at eleven is a powerful character choice.")],
        "believers": ["maya", "sam"],
    },
    {
        "author": "maya",
        "category": "alcohol",
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 6,
        "body": "Week one of acting like someone who just doesn't drink. Ordered a soda at the work thing and nobody noticed.",
        "comments": [("theo", "The soda move works. I believe you.")],
        "believers": ["theo"],
    },
    {
        "author": "theo",
        "category": "gaming",
        "report_type": "daily",
        "visibility": "circle",
        "days_ago": 3,
        "body": "Deleted the launcher again. Maya, ask me about it on Friday.",
        "comments": [("maya", "Friday. I'm asking.")],
        "believers": ["maya"],
    },
    {
        "author": "maya",
        "category": "alcohol",
        "report_type": "daily",
        "visibility": "circle",
        "days_ago": 2,
        "body": "Rough night. Stood in the store for ten minutes, then bought seltzer. Telling you because I need someone to know.",
        "comments": [("theo", "Proud of you. Call me next time.")],
        "believers": ["theo"],
    },
    {
        "author": "theo",
        "category": "scrolling",
        "report_type": "post",
        "visibility": "public",
        "days_ago": 1,
        "body": "Moved every social app to page five. I now play someone who reads books on the train. Two chapters in.",
        "comments": [],
        "believers": ["sam"],
    },
    {
        "author": "maya",
        "category": "alcohol",
        "report_type": "daily",
        "visibility": "private",
        "days_ago": 1,
        "body": "Not ready to say this to anyone yet: I still think about it every evening around six.",
        "comments": [],
        "believers": [],
    },
    {
        "author": "sam",
        "category": None,
        "report_type": "post",
        "visibility": "public",
        "days_ago": 0,
        "body": "Day 2 of pretending I don't care what's on my feed. Screen time is down an hour.",
        "comments": [],
        "believers": ["theo"],
    },
]


def seed():
    if db.session.scalar(db.select(User).filter_by(username="maya")):
        print("Demo data is already there.")
        return

    categories = {category.slug: category for category in db.session.scalars(db.select(Category))}
    users = {
        username: User(
            username=username,
            email=f"{username}@example.com",
            password_hash=generate_password_hash(PASSWORD),
            terms_version=TERMS_VERSION,
        )
        for username in USERS
    }
    db.session.add_all(users.values())
    db.session.flush()

    for username, communities in USERS.items():
        for slug, days in communities.items():
            db.session.add(
                Membership(
                    user_id=users[username].id,
                    category_id=categories[slug].id,
                    started_on=date.today() - timedelta(days=days),
                )
            )

    for requester, addressee, accepted in CIRCLE_LINKS:
        db.session.add(
            CircleLink(requester_id=users[requester].id, addressee_id=users[addressee].id, accepted=accepted)
        )

    now = datetime.now(timezone.utc)
    for item in POSTS:
        post = Post(
            author=users[item["author"]],
            category=categories[item["category"]] if item["category"] else None,
            report_type=item["report_type"],
            visibility=item["visibility"],
            body=item["body"],
            created_at=now - timedelta(days=item["days_ago"]),
        )
        post.comments = [Comment(author=users[name], body=body) for name, body in item["comments"]]
        post.reactions = [Reaction(user_id=users[name].id) for name in item["believers"]]
        db.session.add(post)

    db.session.commit()
    print(f"Added {', '.join(USERS)}. Every password is {PASSWORD}.")
