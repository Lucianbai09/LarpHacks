from datetime import date, datetime, timedelta, timezone

from PIL import Image, ImageDraw
from werkzeug.security import generate_password_hash

from . import db
from .badges import new_badges
from .models import (
    TERMS_VERSION,
    Category,
    CheckIn,
    CircleLink,
    Comment,
    Membership,
    Post,
    PostPhoto,
    Reaction,
    User,
    init_db,
)
from .photos import to_jpeg

# Public on purpose. These accounts are walled off from real ones.
PASSWORD = "larping123"  # nosec B105

# example.com is reserved, so these can never be anyone's real address. Real sign-ups can't use it.
DEMO_EMAIL_DOMAIN = "example.com"

# Username, then each community they're in and their days in character.
USERS = {
    "maya": {"alcohol": 12},
    "theo": {"gaming": 50, "scrolling": 4},
    "sam": {"scrolling": 2, "vaping": 9, "energy-drinks": 4},
    "jonas": {"alcohol": 92, "weed": 33},
    "priya": {"scrolling": 16, "shopping": 21},
    "lena": {"gaming": 8, "gambling": 6},
}

# Requester, addressee, accepted. Two circles, and two requests still waiting.
CIRCLE_LINKS = [
    ("maya", "theo", True),
    ("jonas", "priya", True),
    ("sam", "maya", False),
    ("lena", "theo", False),
]

# Days ago, mood out of 10, and where they stayed in character. Today stays open, so a check-in can be done on stage.
CHECK_INS = {
    "maya": [
        (6, 4, ["alcohol"]),
        (5, 6, ["alcohol"]),
        (4, 3, []),
        (3, 6, ["alcohol"]),
        (2, 5, ["alcohol"]),
        (1, 8, ["alcohol"]),
    ],
    "theo": [(3, 6, ["gaming", "scrolling"]), (2, 7, ["gaming", "scrolling"]), (1, 8, ["gaming", "scrolling"])],
}

POSTS = [
    {
        "author": "sam",
        "communities": ["vaping"],
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 2,
        "body": "A week off the vape. Gave it to my roommate to hide and told him not to tell me where, even if I beg. I begged once. He held the line.",
        "comments": [("lena", "Your roommate is the real MVP.")],
        "believers": ["lena", "theo"],
    },
    {
        "author": "lena",
        "communities": ["gambling"],
        "report_type": "daily",
        "visibility": "public",
        "days_ago": 3,
        "body": "Deleted the betting app during the game tonight instead of after it. Watched the whole thing for fun, like a normal person. Weird feeling. Good feeling.",
        "comments": [],
        "believers": ["sam", "jonas"],
    },
    {
        "author": "priya",
        "communities": ["shopping"],
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 5,
        "body": "Two weeks of the 48-hour rule. If I still want it two days later I can buy it. So far the cart has emptied itself every time.",
        "comments": [("sam", "Trying this one tonight.")],
        "believers": ["maya", "lena"],
    },
    {
        "author": "jonas",
        "communities": ["weed"],
        "report_type": "reflection",
        "visibility": "public",
        "days_ago": 7,
        "body": "Almost a month in and I'm remembering my dreams again. Also turns out I'm a morning person? Nobody is more surprised than me.",
        "comments": [],
        "believers": ["priya", "theo"],
    },
    {
        "author": "sam",
        "communities": ["energy-drinks"],
        "report_type": "daily",
        "visibility": "public",
        "days_ago": 1,
        "body": "Swapped the 3pm energy drink for a walk around the block. Headache on day two, but slept before midnight for the first time in months.",
        "comments": [],
        "believers": ["priya"],
    },
    {
        "author": "theo",
        "communities": ["gaming", "scrolling"],
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 2,
        "body": "Same report for both of my communities, because it's the same problem. Less time on screens, more time asleep. The character is getting boring, and I love it.",
        "comments": [],
        "believers": ["lena", "priya"],
    },
    {
        "author": "priya",
        "communities": ["scrolling"],
        "report_type": "reflection",
        "visibility": "public",
        "days_ago": 3,
        "body": "I watched the sun come up from the kitchen this morning instead of reading about other people's mornings. I'm happier now. Not all the time, but more than I was.",
        "photo": True,
        "comments": [("sam", "This is the kind of morning I'm after.")],
        "believers": ["sam", "lena"],
    },
    {
        "author": "theo",
        "communities": ["gaming", "scrolling"],
        "report_type": "checkin",
        "visibility": "circle",
        "days_ago": 1,
        "body": "Feeling 8/10. Stayed in character: Gaming, Scrolling.",
        "comments": [],
        "believers": ["maya"],
    },
    {
        "author": "jonas",
        "communities": ["alcohol"],
        "report_type": "monthly",
        "visibility": "public",
        "days_ago": 30,
        "body": "Two months. At first I was just playing someone who orders tonic water. Last week a friend asked how long I'd been sober and I had to stop and count.",
        "comments": [("maya", "This is what I'm aiming for.")],
        "believers": ["maya", "theo", "priya"],
    },
    {
        "author": "theo",
        "communities": ["gaming"],
        "report_type": "monthly",
        "visibility": "public",
        "days_ago": 20,
        "body": "One month without ranked. I told people I was the kind of person who goes to bed at eleven, and now I kind of am.",
        "comments": [("maya", "Going to bed at eleven is a powerful character choice.")],
        "believers": ["maya", "sam", "lena"],
    },
    {
        "author": "priya",
        "communities": ["scrolling"],
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 14,
        "body": "Two weeks with my phone charging in the kitchen overnight. I play someone who wakes up and reads the news on paper. It's slow and I like it.",
        "comments": [("sam", "Stealing the kitchen charger idea.")],
        "believers": ["sam", "theo", "jonas"],
    },
    {
        "author": "jonas",
        "communities": ["alcohol"],
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 9,
        "body": "Weddings are the hard level. I brought my own drinks and left before the last hour. The character has boundaries.",
        "comments": [("theo", "The character is doing great.")],
        "believers": ["maya"],
    },
    {
        "author": "maya",
        "communities": ["alcohol"],
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 6,
        "body": "Week one of acting like someone who just doesn't drink. Ordered a soda at the work thing and nobody noticed.",
        "comments": [("theo", "The soda move works. I believe you.")],
        "believers": ["theo", "jonas"],
    },
    {
        "author": "lena",
        "communities": ["gaming"],
        "report_type": "daily",
        "visibility": "public",
        "days_ago": 5,
        "body": "Day 3. Told my group I'm busy with a work thing for a while. Not totally honest yet, but I logged off before midnight.",
        "comments": [("theo", "Deleting the launcher helped me. Happy to compare notes.")],
        "believers": ["theo"],
    },
    {
        "author": "priya",
        "communities": ["scrolling"],
        "report_type": "daily",
        "visibility": "public",
        "days_ago": 4,
        "body": "Caught myself opening the app on autopilot four times today. Closed it four times. That counts.",
        "comments": [],
        "believers": ["sam", "jonas"],
    },
    {
        "author": "theo",
        "communities": ["gaming"],
        "report_type": "daily",
        "visibility": "circle",
        "days_ago": 3,
        "body": "Deleted the launcher again. Maya, ask me about it on Friday.",
        "comments": [("maya", "Friday. I'm asking.")],
        "believers": ["maya"],
    },
    {
        "author": "jonas",
        "communities": ["alcohol"],
        "report_type": "daily",
        "visibility": "circle",
        "days_ago": 3,
        "body": "Tough call with my brother today. Wanted a drink after. Texted Priya instead.",
        "comments": [("priya", "Glad you did. Anytime.")],
        "believers": ["priya"],
    },
    {
        "author": "maya",
        "communities": ["alcohol"],
        "report_type": "daily",
        "visibility": "circle",
        "days_ago": 2,
        "body": "Rough night. Stood in the store for ten minutes, then bought seltzer. Telling you because I need someone to know.",
        "comments": [("theo", "Proud of you. Call me next time.")],
        "believers": ["theo"],
    },
    {
        "author": "priya",
        "communities": [],
        "report_type": "post",
        "visibility": "public",
        "days_ago": 2,
        "body": "Not a report, just something nobody warned me about: quitting gives you a lot of boring evenings. Learning to cook has been the fix so far.",
        "comments": [("lena", "Any easy recipes?")],
        "believers": ["maya"],
    },
    {
        "author": "sam",
        "communities": ["scrolling"],
        "report_type": "daily",
        "visibility": "public",
        "days_ago": 1,
        "body": "Day 1. Deleted the apps from my phone. Keeping the web versions for now, so let's call this a soft launch.",
        "comments": [],
        "believers": ["priya"],
    },
    {
        "author": "lena",
        "communities": ["gaming"],
        "report_type": "weekly",
        "visibility": "public",
        "days_ago": 1,
        "body": "First full week. I kept reaching for the controller after dinner, so I started going for a walk instead. My character apparently goes for walks now.",
        "comments": [],
        "believers": ["theo", "priya", "maya"],
    },
    {
        "author": "theo",
        "communities": ["scrolling"],
        "report_type": "post",
        "visibility": "public",
        "days_ago": 1,
        "body": "Moved every social app to page five. I now play someone who reads books on the train. Two chapters in.",
        "comments": [],
        "believers": ["sam"],
    },
    {
        "author": "maya",
        "communities": ["alcohol"],
        "report_type": "daily",
        "visibility": "private",
        "days_ago": 1,
        "body": "Not ready to say this to anyone yet: I still think about it every evening around six.",
        "comments": [],
        "believers": [],
    },
    {
        "author": "priya",
        "communities": ["scrolling"],
        "report_type": "daily",
        "visibility": "private",
        "days_ago": 1,
        "body": "I still check my old account sometimes. I'm not ready to tell anyone yet.",
        "comments": [],
        "believers": [],
    },
    {
        "author": "sam",
        "communities": [],
        "report_type": "post",
        "visibility": "public",
        "days_ago": 0,
        "body": "Day 2 of pretending I don't care what's on my feed. Screen time is down an hour.",
        "comments": [],
        "believers": ["theo"],
    },
]


def sunrise_photo():
    """Drawn here, so the demo has a photo post without keeping an image file in the repo."""
    image = Image.new("RGB", (1280, 720), "#FFD0A6")
    draw = ImageDraw.Draw(image)
    draw.ellipse((820, 170, 1050, 400), fill="#FFF0DF")
    draw.ellipse((-400, 430, 800, 1200), fill="#F9A66C")
    draw.ellipse((500, 470, 1800, 1200), fill="#F9A66C")
    draw.ellipse((-300, 590, 1500, 1300), fill="#ED7D3A")
    return to_jpeg(image)


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
            categories=[categories[slug] for slug in item["communities"]],
            report_type=item["report_type"],
            visibility=item["visibility"],
            body=item["body"],
            created_at=now - timedelta(days=item["days_ago"]),
        )
        post.comments = [Comment(author=users[name], body=body) for name, body in item["comments"]]
        post.reactions = [Reaction(user_id=users[name].id) for name in item["believers"]]
        if item.get("photo"):
            post.photo = PostPhoto(data=sunrise_photo())
        db.session.add(post)

    for username, check_ins in CHECK_INS.items():
        for days_ago, mood, larped in check_ins:
            db.session.add(
                CheckIn(
                    user_id=users[username].id,
                    day=date.today() - timedelta(days=days_ago),
                    mood=mood,
                    on_track=len(larped) == len(USERS[username]),
                    larped=[categories[slug] for slug in larped],
                )
            )

    for user in users.values():
        new_badges(user)

    # One commit, so a failure anywhere above leaves nothing half-added.
    db.session.commit()
    print(f"Added {', '.join(USERS)}. Every password is {PASSWORD}.")


def clear():
    result = db.session.execute(db.delete(User).where(User.is_demo))
    db.session.commit()
    print(f"Removed {result.rowcount} demo accounts and everything attached to them.")
