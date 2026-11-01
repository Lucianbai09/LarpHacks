import pytest

from app import db
from app.demo import CIRCLE_LINKS, DEMO_EMAIL_DOMAIN, PASSWORD, POSTS, USERS, clear, seed
from app.models import CATEGORIES, REPORT_TYPES, VISIBILITIES, CircleLink, Comment, Post, User


def run(app, action):
    with app.app_context():
        action()


# ---- Seeding never touches real data


def test_seed_marks_everything_as_demo_and_is_safe_to_rerun(app, count):
    run(app, seed)
    assert count(User) == len(USERS) and count(Post) == len(POSTS)
    run(app, seed)
    assert count(User) == len(USERS) and count(Post) == len(POSTS)
    with app.app_context():
        assert all(user.is_demo for user in db.session.scalars(db.select(User)))


def test_seeding_and_clearing_leave_real_people_alone(app, make_user, visitor, get_user, post_id, count):
    alice = make_user("alice")
    bobby = make_user("bobby")
    alice.add("bobby")
    bobby.add("alice")
    alice.write("real-public", "public")
    alice.write("real-circle", "circle")
    alice.write("real-private", "private")
    bobby.post(f"/posts/{post_id('real-public')}/comment", {"body": "real-comment"})
    alice.post("/categories/alcohol/join")
    before = get_user("alice")

    run(app, seed)
    after = get_user("alice")
    assert (after.email, after.password_hash, after.created_at) == (before.email, before.password_hash, before.created_at)
    assert count(Post) == 3 + len(POSTS)

    run(app, clear)
    assert count(User) == 2 and count(Post) == 3 and count(Comment) == 1 and count(CircleLink) == 1
    assert alice.logged_in() and bobby.logged_in()
    assert "real-circle" in bobby.text("/") and "real-private" in alice.text("/")
    assert "in character" in alice.text("/u/alice")


def test_clearing_twice_or_with_nothing_seeded_is_harmless(app, make_user, count):
    make_user("alice")
    run(app, clear)
    run(app, seed)
    run(app, clear)
    run(app, clear)
    assert count(User) == 1 and count(Post) == 0


def test_seed_refuses_rather_than_mixing_with_a_real_account(app, count, visitor):
    with app.app_context():
        db.session.add(User(username="maya", email="real.maya@mail.test", password_hash="x", terms_version="x"))
        db.session.commit()
    run(app, seed)
    assert count(User) == 1 and count(Post) == 0, "nothing half-added"


def test_clearing_removes_real_comments_on_demo_posts_but_not_real_posts(app, seeded, make_user, count):
    alice = make_user("alice")
    alice.write("real-post")
    with app.app_context():
        target = db.session.scalar(db.select(Post.id).where(Post.body.like("%Ordered a soda%")))
    alice.post(f"/posts/{target}/comment", {"body": "on a demo post"})
    run(app, clear)
    assert count(Post) == 1 and count(Comment) == 0
    assert "real-post" in alice.text("/")


# ---- The public password can't reach real people


@pytest.mark.parametrize("username", list(USERS))
def test_real_people_cannot_claim_demo_usernames(visitor, username):
    response = visitor().register(username, f"{username}@mail.test")
    assert response.status_code == 400 and b"username is taken" in response.data


def test_real_people_cannot_use_the_demo_email_domain(visitor, get_user):
    response = visitor().register("alice", f"alice@{DEMO_EMAIL_DOMAIN}")
    assert response.status_code == 400 and b"real email" in response.data
    assert get_user("alice") is None


def test_real_and_demo_accounts_cannot_form_a_circle(seeded, make_user, visitor, count):
    alice = make_user("alice")
    maya = visitor()
    maya.login("maya", PASSWORD)
    links = count(CircleLink)

    assert b"be in the same circle" in alice.add("maya").data
    assert b"be in the same circle" in maya.add("alice").data
    assert count(CircleLink) == links
    assert "Add to circle" not in alice.text("/u/maya")
    assert "Add to circle" not in maya.text("/u/alice")


def test_logging_in_as_a_demo_account_cannot_read_real_private_posts(seeded, make_user, visitor):
    alice = make_user("alice")
    alice.write("alice-circle", "circle")
    alice.write("alice-private", "private")
    maya = visitor()
    maya.login("maya", PASSWORD)
    for path in ["/", "/u/alice", "/categories/alcohol", "/circle"]:
        html = maya.text(path)
        assert "alice-circle" not in html and "alice-private" not in html


def test_demo_accounts_cannot_write_on_real_posts_but_can_read_public_ones(seeded, make_user, visitor, post_id, count):
    alice = make_user("alice")
    alice.write("alice-public", "public")
    target = post_id("alice-public")
    maya = visitor()
    maya.login("maya", PASSWORD)
    comments = count(Comment)

    assert maya.post(f"/posts/{target}/comment", {"body": "vandalism"}).status_code == 403
    assert maya.post(f"/posts/{target}/believe", {"next": "/"}).status_code == 403
    assert count(Comment) == comments
    page = maya.text(f"/posts/{target}")
    assert "alice-public" in page and "can't comment" in page and 'name="body"' not in page


def test_real_people_can_interact_with_demo_posts(app, seeded, make_user):
    alice = make_user("alice")
    with app.app_context():
        target = db.session.scalar(db.select(Post.id).where(Post.body.like("%Ordered a soda%")))
    assert alice.post(f"/posts/{target}/comment", {"body": "nice"}).status_code == 302
    assert alice.post(f"/posts/{target}/believe", {"next": "/"}).status_code == 302


def test_demo_accounts_are_locked(seeded, visitor, get_user, outbox):
    original = get_user("maya").password_hash
    maya = visitor()
    assert maya.login("maya", PASSWORD).status_code == 302
    assert "shared demo account" in maya.text("/account")
    maya.set_password("hijacked1")
    maya.post("/account/delete")
    assert get_user("maya").password_hash == original

    visitor().post("/forgot-password", {"email": f"maya@{DEMO_EMAIL_DOMAIN}"})
    assert outbox == [], "no reset link for a demo account"
    assert visitor().login("maya", PASSWORD).status_code == 302


def test_demo_accounts_are_labelled_so_nobody_mistakes_them_for_real_people(seeded, make_user, visitor):
    html = visitor().text("/u/maya")
    assert "<small>demo</small>" in html
    assert "<small>demo</small>" in visitor().text("/")
    alice = make_user("alice")
    assert "<small>demo</small>" not in visitor().text("/u/alice")
    assert alice.logged_in()


# ---- The demo story itself


@pytest.mark.parametrize(
    "who, sees, misses",
    [
        ("maya", ["Ordered a soda", "Stood in the store", "every evening around six", "Deleted the launcher"], ["check my old account"]),
        ("theo", ["Ordered a soda", "Stood in the store"], ["every evening around six", "Texted Priya"]),
        ("jonas", ["Ordered a soda", "Texted Priya"], ["Stood in the store", "check my old account"]),
        ("sam", ["Ordered a soda"], ["Stood in the store", "every evening around six", "Texted Priya"]),
    ],
)
def test_demo_accounts_show_the_audiences_working(seeded, visitor, who, sees, misses):
    browser = visitor()
    assert browser.login(who, PASSWORD).status_code == 302
    html = browser.text("/")
    for text in sees:
        assert text in html, f"{who} should see {text}"
    for text in misses:
        assert text not in html, f"{who} should not see {text}"


def test_logged_out_visitors_only_see_public_demo_posts(seeded, visitor):
    html = visitor().text("/")
    assert "Ordered a soda" in html
    assert "Stood in the store" not in html and "every evening around six" not in html


def test_every_community_has_demo_posts(seeded, visitor):
    for slug, *_ in CATEGORIES:
        assert "<article" in visitor().text(f"/categories/{slug}"), slug


def test_demo_requests_are_waiting_to_be_accepted_on_stage(seeded, visitor):
    maya = visitor()
    maya.login("maya", PASSWORD)
    assert "Circle (1)" in maya.text("/")
    assert b"is in your circle" in maya.add("sam").data


def test_the_seed_list_is_consistent():
    assert all(item["author"] in USERS for item in POSTS)
    assert all(item["report_type"] in REPORT_TYPES and item["visibility"] in VISIBILITIES for item in POSTS)
    assert all(name in USERS for item in POSTS for name in item["believers"])
    assert all(name in USERS for item in POSTS for name, _ in item["comments"])
    assert all(a in USERS and b in USERS for a, b, _ in CIRCLE_LINKS)
