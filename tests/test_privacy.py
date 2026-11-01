from datetime import date, timedelta

from app import db
from app.models import CheckIn, CircleLink, Membership, Post, User

BODIES = {"public": "BODY-public-xyz", "circle": "BODY-circle-xyz", "private": "BODY-private-xyz"}
READERS = {
    "public": {"author", "friend", "stranger", "pending", "anon"},
    "circle": {"author", "friend"},
    "private": {"author"},
}


def cast(make_user, visitor):
    people = {name: make_user(name) for name in ["author", "friend", "stranger", "pending"]}
    people["author"].add("friend")
    people["friend"].add("author")
    people["pending"].add("author")
    for visibility, body in BODIES.items():
        people["author"].write(body, visibility)
    people["anon"] = visitor()
    return people


def test_each_audience_reaches_exactly_the_right_people_on_every_page(make_user, visitor, post_id):
    people = cast(make_user, visitor)
    for visibility, body in BODIES.items():
        for name, browser in people.items():
            allowed = name in READERS[visibility]
            for path in ["/", "/categories/alcohol", "/u/author"]:
                assert (body in browser.text(path)) == allowed, f"{visibility} {name} {path}"
            status = browser.c.get(f"/posts/{post_id(body)}").status_code
            assert status == (200 if allowed else 404), f"{visibility} {name} direct URL"


def test_people_cannot_interact_with_posts_they_cannot_see(make_user, visitor, post_id):
    people = cast(make_user, visitor)
    for visibility, name in [("private", "friend"), ("circle", "stranger"), ("circle", "pending")]:
        target = post_id(BODIES[visibility])
        assert people[name].post(f"/posts/{target}/believe", {"next": "/"}).status_code == 404
        assert people[name].post(f"/posts/{target}/comment", {"body": "x"}).status_code == 404


def test_write_needs_login_and_defaults_to_the_circle(make_user, visitor):
    assert visitor().c.get("/write").status_code == 302
    html = make_user("author").text("/write")
    assert 'value="circle" checked' in " ".join(html.split())


def test_write_rejects_bad_input_and_keeps_the_text(make_user, count):
    browser = make_user("author")
    for data in [
        {"body": "  ", "visibility": "public", "report_type": "post"},
        {"body": "x", "visibility": "everyone", "report_type": "post"},
        {"body": "x", "report_type": "post"},
        {"body": "x", "visibility": "public", "report_type": "hourly"},
        {"body": "x", "visibility": "public", "report_type": "post", "category": "nope"},
        {"body": "x" * 5001, "visibility": "public", "report_type": "post"},
    ]:
        assert browser.post("/write", data).status_code == 400, data
    assert count(Post) == 0
    html = browser.post("/write", {"body": "keep-me", "visibility": "private", "report_type": "weekly", "category": "nope"}).get_data(as_text=True)
    assert "keep-me</textarea>" in html and 'value="private" checked' in " ".join(html.split())


def test_comments_have_a_length_limit(make_user, post_id, app):
    browser = make_user("author")
    browser.write("a post")
    target = post_id("a post")
    response = browser.post(f"/posts/{target}/comment", {"body": "x" * 2001}, follow_redirects=True)
    assert b"up to 2000" in response.data and b"x" * 2001 not in response.data
    assert browser.post(f"/posts/{target}/comment", {"body": "x" * 2000}, follow_redirects=True).status_code == 200


def test_overall_posts_only_show_on_the_home_feed(make_user, visitor):
    browser = make_user("author")
    assert browser.write("overall-post", category="").headers["Location"] == "/"
    assert "overall-post" in visitor().text("/")
    assert "overall-post" not in visitor().text("/categories/alcohol")


def test_a_post_can_go_in_several_communities_or_overall_but_not_both(make_user, visitor, count):
    browser = make_user("author")
    fields = {"visibility": "public", "report_type": "weekly"}
    assert browser.post("/write", {**fields, "body": "both-post", "category": ["alcohol", "gaming"]}).headers["Location"] == "/"
    for slug, shown in [("alcohol", True), ("gaming", True), ("scrolling", False)]:
        assert ("both-post" in visitor().text(f"/categories/{slug}")) == shown, slug
    assert visitor().text("/").count("both-post") == 1

    assert browser.post("/write", {**fields, "body": "x", "category": ["", "alcohol"]}).status_code == 400
    assert browser.post("/write", {**fields, "body": "x", "category": ["alcohol", "nope"]}).status_code == 400
    assert count(Post) == 1


def test_believing_from_the_page_answers_without_a_redirect(make_user, post_id, visitor):
    browser = make_user("author")
    browser.write("a post")
    target = post_id("a post")
    press = lambda: browser.post(f"/posts/{target}/believe", headers={"X-Requested-With": "fetch"})
    assert press().get_json() == {"believed": True, "believers": 1, "badges": []}, "your own post doesn't earn Cheerleader"
    assert "You believe this (1)" in browser.text(f"/posts/{target}")
    assert press().get_json() == {"believed": False, "believers": 0, "badges": []}

    fan = make_user("fan")
    reply = fan.post(f"/posts/{target}/believe", headers={"X-Requested-With": "fetch"}).get_json()
    assert reply["believers"] == 1 and reply["badges"] == ["Cheerleader"]
    assert "I believe you (1)" in visitor().text(f"/posts/{target}"), "and everyone else sees it next time they load the page"


def test_setup_steps_join_communities_and_save_the_pledge_and_audience(make_user, visitor):
    alice = make_user("alice")
    assert alice.post("/setup/1", {}, token_from="/setup/1").status_code == 400
    assert alice.post("/setup/1", {"habit": ["alcohol", "nope"]}, token_from="/setup/1").status_code == 400
    assert alice.post("/setup/1", {"habit": ["alcohol", "gaming"]}, token_from="/setup/1").headers["Location"] == "/setup/2"
    assert "I&#39;m someone who doesn&#39;t game on autopilot or need a drink." in alice.text("/setup/2")

    assert alice.post("/setup/2", {"pledge": "x" * 201, "shared": "on"}, token_from="/setup/2").status_code == 400
    assert alice.post("/setup/2", {"pledge": "I go to bed early now.", "shared": "on"}, token_from="/setup/2").headers["Location"] == "/setup/3"
    assert alice.post("/setup/3", {"visibility": "private"}, token_from="/setup/3").headers["Location"] == "/"
    assert 'value="private" checked' in " ".join(alice.text("/write").split())
    assert alice.c.get("/setup/9").status_code == 404

    alice.post("/setup/1", {"habit": ["gaming"]}, token_from="/setup/1")
    assert "1 day" not in alice.text("/categories/alcohol") and 'action="/categories/alcohol/join"' in alice.text("/categories/alcohol")


def test_a_pledge_is_only_shown_to_you_and_your_circle(make_user, visitor):
    alice = make_user("alice")
    friend = make_user("friend")
    stranger = make_user("stranger")
    alice.add("friend")
    friend.add("alice")

    assert "already quit" in alice.text("/u/alice"), "there's always a suggested pledge to start from"
    alice.post("/pledge", {"pledge": "pledge-words", "shared": "on"})
    assert "pledge-words" in alice.text("/u/alice") and "pledge-words" in friend.text("/u/alice")
    for viewer in [stranger, visitor()]:
        assert "pledge-words" not in viewer.text("/u/alice")

    alice.post("/pledge", {"pledge": "pledge-words"})
    assert "pledge-words" in alice.text("/u/alice") and "pledge-words" not in friend.text("/u/alice")

    assert b"up to 200" in alice.post("/pledge", {"pledge": "x" * 201}, follow_redirects=True).data
    assert "pledge-words" in alice.text("/u/alice")


def test_badges_are_earned_once_and_only_you_see_them(make_user, app):
    alice = make_user("alice")
    bobby = make_user("bobby")
    answers = {"mood": "8", "visibility": "private"}
    assert "New badge: First step" in alice.post("/check-in", answers, follow_redirects=True).get_data(as_text=True)
    assert "New badge" not in alice.post("/check-in", answers, follow_redirects=True).get_data(as_text=True)

    page = alice.text("/u/alice")
    assert 'id="badges"' in page and "1 of 10 earned" in page and "First step" in page
    assert 'id="badges"' not in bobby.text("/u/alice")

    alice.add("bobby")
    assert "New badge: Partnered up" in bobby.add("alice").get_data(as_text=True)

    # Seven days in a row, with a slip and a comeback along the way.
    with app.app_context():
        user = db.session.scalar(db.select(User).filter_by(username="alice"))
        db.session.execute(db.delete(CheckIn))
        for ago in range(1, 9):
            db.session.add(CheckIn(user_id=user.id, day=date.today() - timedelta(days=ago), mood=8, on_track=ago != 8))
        db.session.commit()
    earned = alice.post("/check-in", answers, follow_redirects=True).get_data(as_text=True)
    for name in ["Honest day", "Comeback", "Perfect week"]:
        assert f"New badge: {name}" in earned, name


def test_belief_toggles_and_returns_to_the_post(make_user, post_id):
    browser = make_user("author")
    browser.write("a post")
    target = post_id("a post")
    response = browser.post(f"/posts/{target}/believe", {"next": "/categories/alcohol"})
    assert response.headers["Location"] == f"/categories/alcohol#post-{target}"
    assert "You believe this (1)" in browser.text(f"/posts/{target}")
    browser.post(f"/posts/{target}/believe", {"next": "/"})
    assert "I believe you (0)" in browser.text(f"/posts/{target}")
    assert browser.post(f"/posts/{target}/believe", {"next": "//evil.test"}).headers["Location"].startswith("/#post-")


# ---- Adding friends


def test_circle_request_and_accept(make_user, count):
    alice = make_user("alice")
    bobby = make_user("bobby")
    assert b"Request sent to bobby" in alice.add("bobby").data
    assert "Circle (1)" in bobby.text("/") and "Accept" in bobby.text("/circle")
    assert "Cancel" in alice.text("/circle")

    alice.add("bobby")
    assert count(CircleLink) == 1, "asking twice doesn't duplicate"
    assert b"is in your circle" not in alice.add("bobby").data, "you can't accept your own request"

    assert b"is in your circle" in bobby.add("alice").data
    assert "Circle (" not in bobby.text("/")
    assert "bobby" in alice.text("/circle") and "alice" in bobby.text("/circle")


def test_friends_can_be_added_from_a_profile_page(make_user):
    alice = make_user("alice")
    bobby = make_user("bobby")
    assert "Add to circle" in alice.text("/u/bobby")
    alice.add("bobby")
    assert "Circle request sent" in alice.text("/u/bobby")
    assert "Wants to join your circle" in bobby.text("/u/alice")
    bobby.add("alice")
    assert "Remove from circle" in bobby.text("/u/alice")


def test_circle_page_shows_your_username_to_share(make_user):
    assert "<strong>alice</strong>" in make_user("alice").text("/circle")


def test_you_cannot_add_yourself_or_nobody(make_user, count):
    alice = make_user("alice")
    assert b"No one else" in alice.add("alice").data
    assert b"No one else" in alice.add("ghost").data
    assert count(CircleLink) == 0


def test_decline_and_cancel(make_user, count):
    alice = make_user("alice")
    bobby = make_user("bobby")
    alice.add("bobby")
    bobby.remove("alice")
    assert count(CircleLink) == 0
    alice.add("bobby")
    alice.remove("bobby")
    assert count(CircleLink) == 0


def test_removing_someone_closes_everything_at_once(make_user, post_id, visitor):
    alice = make_user("alice")
    bobby = make_user("bobby")
    alice.add("bobby")
    bobby.add("alice")
    alice.write("circle-secret", "circle")
    alice.post("/categories/alcohol/join")
    target = post_id("circle-secret")
    bobby.post(f"/posts/{target}/comment", {"body": "bobby-comment"})
    bobby.post(f"/posts/{target}/believe", {"next": "/"})
    assert "circle-secret" in bobby.text("/u/bobby") and "bobby-comment" in bobby.text("/u/bobby")
    assert "in character" in bobby.text("/u/alice")

    bobby.remove("alice")
    assert bobby.c.get(f"/posts/{target}").status_code == 404
    assert "circle-secret" not in bobby.text("/")
    history = bobby.text("/u/bobby")
    assert "circle-secret" not in history and "bobby-comment" not in history
    assert "in character" not in bobby.text("/u/alice")


# ---- Daily check-ins


CHECK_IN = {"mood": "8", "visibility": "private"}


def test_check_ins_stay_private_until_shared(make_user, visitor, count):
    alice = make_user("alice")
    bobby = make_user("bobby")
    alice.add("bobby")
    bobby.add("alice")

    assert alice.post("/check-in", CHECK_IN).status_code == 302
    assert "You checked in today" in alice.text("/") and "Feeling 8/10" in alice.text("/")
    assert count(Post) == 0 and "1/1" in alice.text("/progress")
    assert "1/1" not in bobby.text("/progress"), "your progress page is only ever your own"

    alice.post("/check-in", {**CHECK_IN, "mood": "10", "visibility": "circle"})
    assert count(CheckIn) == 1 and count(Post) == 1, "one a day, and answering again updates it"
    assert "Feeling 10/10" in bobby.text("/") and "Feeling 10/10" not in visitor().text("/")

    alice.post("/check-in", {**CHECK_IN, "mood": "3", "visibility": "circle"})
    assert count(Post) == 1 and "Feeling 3/10" in bobby.text("/") and "Feeling 10/10" not in bobby.text("/")

    alice.post("/check-in", CHECK_IN)
    assert count(CheckIn) == 1 and count(Post) == 0 and "Feeling" not in bobby.text("/")


def test_check_in_refuses_bad_answers_and_keeps_good_ones(make_user, count):
    browser = make_user("alice")
    for bad in [{"mood": "11"}, {"mood": "0"}, {"mood": "x"}, {"larped": "alcohol"}, {"visibility": "everyone"}]:
        assert browser.post("/check-in", {**CHECK_IN, **bad}).status_code == 400, bad
    assert count(CheckIn) == 0
    html = browser.post("/check-in", {**CHECK_IN, "visibility": "everyone"}).get_data(as_text=True)
    assert 'value="8" required checked' in " ".join(html.split())


def test_a_shared_check_in_only_names_and_goes_into_what_you_ticked(make_user, visitor):
    alice = make_user("alice")
    alice.post("/categories/gaming/join")
    alice.post("/categories/alcohol/join")

    alice.post("/check-in", {**CHECK_IN, "larped": ["gaming"], "visibility": "public"})
    assert "Feeling 8/10. Stayed in character: Gaming." in visitor().text("/categories/gaming")
    assert "Feeling 8/10" not in visitor().text("/categories/alcohol"), "and nothing about the one left blank"
    done = alice.text("/check-in")
    assert "I broke character in Alcohol" in done and "I broke character in Gaming" not in done

    alice.post("/check-in", {**CHECK_IN, "larped": ["gaming", "alcohol"], "visibility": "public"})
    assert "I broke character" not in alice.text("/check-in") and "1/1" in alice.text("/progress")

    alice.post("/check-in", {**CHECK_IN, "mood": "3", "visibility": "public"})
    assert "Feeling 8/10" not in visitor().text("/categories/gaming")
    # Logged in, because the logged-out landing page leaves check-ins out.
    assert "Feeling 3/10. Didn&#39;t stay in character today" in make_user("bobby").text("/"), "nothing ticked goes in Overall"


# ---- Communities and counts


def test_joining_counting_and_breaking_character(make_user, app, get_user):
    browser = make_user("alice")
    assert 'action="/categories/alcohol/join"' in browser.text("/categories/alcohol")
    browser.post("/categories/alcohol/join", {"next": "/categories"})
    assert "0 days in character" in browser.text("/categories")
    browser.post("/categories/alcohol/join", {"next": "/categories"})

    def set_days(days):
        with app.app_context():
            membership = db.session.scalar(db.select(Membership))
            membership.started_on = date.today() - timedelta(days=days)
            db.session.commit()

    set_days(1)
    assert "1 day in character" in browser.text("/categories/alcohol")
    set_days(12)
    assert "12 days in character" in browser.text("/categories/alcohol")
    browser.post("/categories/alcohol/restart", {"next": "/categories/alcohol"})
    assert "0 days in character" in browser.text("/categories/alcohol")
    browser.post("/categories/alcohol/leave")
    assert 'action="/categories/alcohol/join"' in browser.text("/categories/alcohol")


def test_ticking_a_community_counts_today_until_you_break_character(make_user):
    browser = make_user("alice")
    browser.post("/categories/alcohol/join")
    browser.post("/check-in", {**CHECK_IN, "larped": ["alcohol"]})
    assert "1 day in character" in browser.text("/")
    browser.post("/categories/alcohol/restart")
    assert "0 days in character" in browser.text("/")


def test_home_is_a_landing_page_until_you_log_in_and_medals_follow_the_count(make_user, visitor, app):
    assert "Sign up free" in visitor().text("/")
    browser = make_user("alice")
    browser.post("/categories/alcohol/join")
    with app.app_context():
        db.session.scalar(db.select(Membership)).started_on = date.today() - timedelta(days=12)
        db.session.commit()
    html = browser.text("/")
    assert "Sign up free" not in html and "12 days in character. 2 more until your 2 weeks medal." in html
    assert html.count("medal-item earned") == 2 and html.count("medal-item next") == 1


def test_unknown_pages_are_404s(make_user, visitor):
    browser = make_user("alice")
    assert browser.post("/categories/nope/join").status_code == 404
    assert visitor().c.get("/categories/nope").status_code == 404
    assert visitor().c.get("/u/ghost").status_code == 404
    assert visitor().c.get("/posts/999999").status_code == 404


def test_what_shows_on_a_profile_depends_on_who_is_looking(make_user, visitor, post_id):
    alice = make_user("alice")
    bobby = make_user("bobby")
    stranger = make_user("stranger")
    alice.add("bobby")
    bobby.add("alice")
    alice.post("/categories/alcohol/join")
    alice.write("a post")
    alice.post(f"/posts/{post_id('a post')}/comment", {"body": "my-own-comment"})

    own = alice.text("/u/alice")
    assert "in character" in own and "my-own-comment" in own and "Posts you believed" in own
    assert "in character" in bobby.text("/u/alice"), "the circle sees communities"
    assert "Comments you left" not in bobby.text("/u/alice"), "only you see your interaction history"
    for viewer in [stranger, visitor()]:
        html = viewer.text("/u/alice")
        assert "in character" not in html and "Comments you left" not in html
