from datetime import date, datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from . import db
from .models import TERMS_VERSION, Category, CircleLink, Comment, Membership, Post, Reaction, User, init_db

# Public on purpose. These accounts are walled off from real ones.
PASSWORD = "larping123"  # nosec B105

# example.com is reserved, so these can never be anyone's real address. Real sign-ups can't use it.
DEMO_EMAIL_DOMAIN = "example.com"

# Username, then each community they're in and their days in character.
USERS = {
    "maya": {"alcohol": 12},
    "theo": {"gaming": 50, "scrolling": 4},
    "sam": {"scrolling": 2},
    "jonas": {"alcohol": 92},
    "priya": {"scrolling": 16},
    "lena": {"gaming": 8},
}

# Requester, addressee, accepted. Two circles, and two requests still waiting.
CIRCLE_LINKS = [
    ("maya", "theo", True),
    ("jonas", "priya", True),
    ("sam", "maya", False),
    ("lena", "theo", False),
]

POSTS = [
    {
        "author": "jonas",
        "category": "alcohol",
        "report_type": "monthly",
        "visibility": "public",
        "days_ago": 30,
        "body": "Two months. At first I was just playing someone who orders tonic water. Last week a friend asked how long I'd been sober and I had to stop and count.",
        "comments": [("maya", "This is what I'm aiming for.")],
        "believers": ["maya", "theo", "priya"],
    },
    {
        "author": "theo",
        "category": "gaming",
        "report_type": "monthly",
        "visibility": "public",
        "days_ago": 20,
        "body": "One month without ranked. I told people I was the kind of person who goes to bed at eleven, and now I kind of am.",
        "comments": [("maya", "Going to bed at eleven is a powerful character choice.")],
        "believers": ["maya", "sam", "lena"],
    },
    {
        "author": "priya",
        "category": "scrolling",
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 14,
        "body": "Two weeks with my phone charging in the kitchen overnight. I play someone who wakes up and reads the news on paper. It's slow and I like it.",
        "comments": [("sam", "Stealing the kitchen charger idea.")],
        "believers": ["sam", "theo", "jonas"],
    },
    {
        "author": "jonas",
        "category": "alcohol",
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 9,
        "body": "Weddings are the hard level. I brought my own drinks and left before the last hour. The character has boundaries.",
        "comments": [("theo", "The character is doing great.")],
        "believers": ["maya"],
    },
    {
        "author": "maya",
        "category": "alcohol",
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 6,
        "body": "Week one of acting like someone who just doesn't drink. Ordered a soda at the work thing and nobody noticed.",
        "comments": [("theo", "The soda move works. I believe you.")],
        "believers": ["theo", "jonas"],
    },
    {
        "author": "lena",
        "category": "gaming",
        "report_type": "daily",
        "visibility": "public",
        "days_ago": 5,
        "body": "Day 3. Told my group I'm busy with a work thing for a while. Not totally honest yet, but I logged off before midnight.",
        "comments": [("theo", "Deleting the launcher helped me. Happy to compare notes.")],
        "believers": ["theo"],
    },
    {
        "author": "priya",
        "category": "scrolling",
        "report_type": "daily",
        "visibility": "public",
        "days_ago": 4,
        "body": "Caught myself opening the app on autopilot four times today. Closed it four times. That counts.",
        "comments": [],
        "believers": ["sam", "jonas"],
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
        "author": "jonas",
        "category": "alcohol",
        "report_type": "daily",
        "visibility": "circle",
        "days_ago": 3,
        "body": "Tough call with my brother today. Wanted a drink after. Texted Priya instead.",
        "comments": [("priya", "Glad you did. Anytime.")],
        "believers": ["priya"],
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
        "author": "priya",
        "category": None,
        "report_type": "post",
        "visibility": "public",
        "days_ago": 2,
        "body": "Not a report, just something nobody warned me about: quitting gives you a lot of boring evenings. Learning to cook has been the fix so far.",
        "comments": [("lena", "Any easy recipes?")],
        "believers": ["maya"],
    },
    {
        "author": "sam",
        "category": "scrolling",
        "report_type": "daily",
        "visibility": "public",
        "days_ago": 1,
        "body": "Day 1. Deleted the apps from my phone. Keeping the web versions for now, so let's call this a soft launch.",
        "comments": [],
        "believers": ["priya"],
    },
    {
        "author": "lena",
        "category": "gaming",
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 1,
        "body": "First full week. I kept reaching for the controller after dinner, so I started going for a walk instead. My character apparently goes for walks now.",
        "comments": [],
        "believers": ["theo", "priya", "maya"],
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
        "author": "priya",
        "category": "scrolling",
        "report_type": "daily",
        "visibility": "private",
        "days_ago": 1,
        "body": "I still check my old account sometimes. I'm not ready to tell anyone yet.",
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
    init_db()

    if db.session.scalar(db.select(User).filter_by(is_demo=True)):
        print("Demo data is already there.")
        return

    taken = db.session.scalars(db.select(User.username).where(User.username.in_(USERS))).all()
    if taken:
        print(f"Not adding demo data, because real accounts already use: {', '.join(taken)}.")
        return

    categories = {category.slug: category for category in db.session.scalars(db.select(Category))}
    users = {
        username: User(
            username=username,
            email=f"{username}@{DEMO_EMAIL_DOMAIN}",
            password_hash=generate_password_hash(PASSWORD),
            is_demo=True,
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

    # One commit, so a failure anywhere above leaves nothing half-added.
    db.session.commit()
    print(f"Added {', '.join(USERS)}. Every password is {PASSWORD}.")


def clear():
    result = db.session.execute(db.delete(User).where(User.is_demo))
    db.session.commit()
    print(f"Removed {result.rowcount} demo accounts and everything attached to them.")
