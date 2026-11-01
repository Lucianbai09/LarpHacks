# Cove: handoff (as of 2026-11-01)

For whoever picks this up next, on any device or Claude account. Claude's memory doesn't move between accounts, so everything needed is here. Setup steps are in `README.md`, and security rules are in `SECURITY.md`.

## 1. How to work with this user

- **Work like a lazy senior dev.** Do the simplest thing that works for the demo. No over-engineering and no long verification rounds.
- **Go easy on testing.** The user wants about 50 tests in total. Add 1 or 2 for what matters, and only run the tests related to a change.
- **It's a hackathon demo, not a real service.** Free and quick wins. No paid services and no legal polish.
- **The user dislikes the terminal.** Lead with what they can click: F5, Ctrl+F5, VS Code's Testing panel, GitHub Desktop, dashboards. If a command is unavoidable, give the exact line using `.venv\Scripts\...`, because PowerShell blocks `Activate.ps1`.
- **Don't commit or push unless asked.** The user commits through GitHub Desktop.
- **Secrets only go in `.env`,** which git ignores. Never put them in chat or in tracked files.
- **If the user's design conflicts with what exists,** go with what's best and tell them what to add later.
- **Keep reports short.** Say what to click first, then what changed, and be plain about anything untested.

## 2. Hackathon and rubric

**Theme:** "Create a product to help you LARP as someone you are not."

**Judging:** six criteria, 5 points each, 30 total.

| Criterion | How we're aiming at it |
| --- | --- |
| Working product | Real accounts, a real database, and flows that work end to end |
| Usefulness | Day counter, daily check-in, Progress page, accountability circle, audience controls |
| Theme | Larp as someone who already quit, until it's true. "Days in character", "I broke character", a pledge written as if it's already true |
| Creativity | "I believe you" instead of likes, medals, and badges that reward honesty as well as clean days |
| Ease of use | Three-question check-in with no typing, one-click reactions, setup steps, stays logged in for 30 days |
| Demo | Seeded accounts and posts so the site never looks empty, with today's check-in left open to do live |

The old weak spots, the plain look and the missing check-in, are fixed. What's left is proving it live: deploy and rehearse.

## 3. The product

**Cove** is an addiction tracker where you post your progress and larp as someone who already quit, until it's true. It's inspired by Strava, BeReal and LinkedIn-style posting. The tagline is "Act like you've already quit."

The product is called Cove, while the repo, databases and Render service keep the name LarpHacks.

- Communities are Alcohol, Scrolling and Gaming, and more must stay easy to add.
- Posts go into any number of communities, or into Overall on its own.
- Real people can sign up and use it alongside walled-off demo data.

## 4. Current state

- **Repo:** github.com/Lucianbai09/LarpHacks, branch `main`. Commit `a95f127` ("commit 4: ui + new features") is pushed.
- **Check this first:** this handoff was written with everything after that commit still uncommitted, including badges, setup steps, the pledge, multi-community posts and the three-question check-in. If `app/badges.py` is missing, the user hasn't pushed yet, so ask them to commit and push from the original machine in GitHub Desktop.
- **Not deployed.** Render comes last, once tables are final.
- **Git doesn't carry these:**
  - `.env`, with keys `DATABASE_URL`, `TEST_DATABASE_URL`, `SECRET_KEY`, `EMAIL_WEBHOOK_URL`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`. On a new device, copy `.env.example`, then copy `EMAIL_WEBHOOK_URL` over by hand or email won't send. The README explains the rest.
  - The local databases. A new device only gets demo data. The user's real account stays on the original machine.
  - `LARP-prototype.html`, the design prototype. Ask the user for it if you build a feature from it.
  - `.venv`, which the README's setup recreates.
- **Running it:** F5 in VS Code runs `run.py` and opens http://127.0.0.1:5000. Saving code or `.env` restarts it. Use Ctrl+F5 for live demos. If the site hangs after an error, press the red square, then F5.
- **Databases (local Postgres 18):** `larphacks` is the real one, and `larphacks_test` gets wiped by the tests.
- **Original machine's data:** `larphacks` holds 1 real account (1 post, 2 communities, 1 check-in, 1 "I believe you" on a demo post) plus the demo data.
- **That machine also has a placeholder global `DATABASE_URL`.** `load_dotenv(override=True)` in `create_app` makes `.env` win.

**Before changing a table:** there are no migrations, and `flask init-db` only creates missing tables. Check for rows where `is_demo` is false. If any exist, change the table in place with `ALTER TABLE` from a throwaway script. Only rebuild a database that holds nothing but demo data.

**Anyone with an older local copy** needs to rebuild, because `check_in` changed. This wipes their local database, so they should stop the site first and check it holds nothing they want:

```
& "C:\Program Files\PostgreSQL\18\bin\dropdb.exe" -U postgres larphacks
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres larphacks
.venv\Scripts\flask.exe init-db
.venv\Scripts\flask.exe seed-demo
```

## 5. Stack

| Part | What |
| --- | --- |
| Language and framework | Python 3.14, Flask 3.1, Jinja2 |
| Database | PostgreSQL 18, Flask-SQLAlchemy, SQLAlchemy 2.1, psycopg 3 |
| Accounts and protection | Flask-Login, Flask-WTF (CSRF), Flask-Limiter, scrypt password hashes |
| Photos | Pillow |
| Front end | Hand-written CSS and a little plain JavaScript. No framework or build step |
| Hosting (planned) | Render's free plan, with gunicorn and free Postgres, set up by `render.yaml` |
| Email | A free Google Apps Script that sends from Gmail, 100 a day, because Render's free plan blocks SMTP |
| Captcha | Cloudflare Turnstile's free plan |
| Automation | GitHub Actions (`security.yml`: pytest, pip-audit, bandit, gunicorn start) and Dependabot |

## 6. Layout

| Path | What's there |
| --- | --- |
| `run.py` | Starts the site, and is what gunicorn loads |
| `app/__init__.py` | App factory, config, `flask init-db`, `seed-demo`, `clear-demo` |
| `app/models.py` | Tables, `CATEGORIES`, `MILESTONES`, `MOODS`, and `visible_to()` |
| `app/views.py` | Feeds, write, check-in, progress, posts, communities, profiles, pledge, setup, circles |
| `app/auth.py` | Register, login, email confirmation, password reset, account page |
| `app/badges.py` | The 10 achievements and what earns each one |
| `app/photos.py` | Cleans uploads by redrawing them as small JPEGs |
| `app/security.py` | Captcha check, password check, security headers |
| `app/mail.py` | Sends email |
| `app/demo.py` | Demo data |
| `app/templates/` | `_ui.html` (icons, medals, charts), `_forms.html` (form macros), `_post.html` (one post), `_icons.html` (icon set) |
| `app/static/` | `style.css` (the whole design system) and `app.js` |
| `tests/` | `test_security`, `test_privacy`, `test_accounts`, `test_demo_data` |

**Tables:** `users`, `profile` (pledge, whether it's shared, starting audience), `category`, `membership` (with `started_on`), `circle_link`, `post`, `post_category`, `post_photo`, `comment`, `reaction`, `check_in` (one per user per day: `mood`, `on_track`, `post_id`), `check_in_category` (the communities ticked), `earned_badge`.

## 7. Features built

**Accounts**
- Register with a username, email, password, terms checkbox and captcha, then land on setup. Any non-blank password works, because the user asked for no password rules.
- Log in with a username or email, and stay logged in for 30 days. Forgot password emails a one-time link that expires in an hour.
- Email confirmation adds a checkmark and blocks nothing.
- The account page has change password, delete account (removes everything of theirs) and a link back to setup.

**Setup steps** (`/setup/1` to `3`): what you're quitting, your pledge, and who sees your progress. Unticking a community on a later visit leaves it and loses its count, and the page says so.

**Home:** last 7 days as dots, today's check-in or a button to do it, a days-in-character card per community with medals, a Write button, circle requests, a badges card and the latest feed.

**Daily check-in** (`/check-in`), one per day and editable. It's exactly three questions, which the user chose on purpose:
1. How are you feeling today? (1 to 10)
2. Where did you stay in character today? (a checkbox per community you're in)
3. Who can see this? (Only me, My circle, Community)

**Progress page** (only you): in character x/y, average mood, hardest day, 7-day dots, mood bars, a bar per community, 30-day stats, and a button that starts a weekly report with your numbers filled in.

**Posts:** types are Post, Daily, Weekly, Monthly and Reflection, with up to 5000 characters and an optional photo (JPG, PNG, WebP or GIF, up to 10 MB). Comments go up to 2000 characters. "I believe you" updates instantly with no reload or scroll, and other people see the new count on their next page load.

**Who can see a post:** Community (anyone, even logged out), My circle, or Only me. Feeds show the latest 50 you're allowed to see.

**Communities:** join or leave. Joining starts a count, and "I broke character" restarts it. Medals come at 1 day, 1 week, 2 weeks, 1 month and 3 months.

**Circles:** add by exact username or from a profile. It needs accepting and is mutual. Removing someone closes access immediately.

**Profiles:** your own shows your communities, counts, pledge, badges, entries, comments and believed posts. Other people's show only the posts you may see, and communities and counts only show to their circle.

**Pledge:** editable on your profile. It starts as a sentence built from your communities, such as "I'm someone who doesn't need a drink or game on autopilot."

**Badges:** First step, Honest day, Comeback, Perfect week, Many fronts, Open book, Cheerleader, Partnered up, Storyteller, Circle of three. Earning one shows a "New badge" message.

**Also:** a landing page for logged-out visitors, `/terms`, `/privacy`, and a "not medical care" footer.

## 8. Decisions already made

Don't undo these without asking.

- **Check-in stays at three questions.** The user removed urges, "hardest part" and mood faces themselves.
- **A shared check-in** goes only into the communities ticked and only names those, or Overall if none are ticked. A slip in one community isn't announced to it.
- **"In character" for a day** means every community was ticked. Ticking 1 of 2 counts as a slip on the dots and for badges, and per-community bars still give credit. It's saved on the row, so joining or leaving later doesn't rewrite history.
- **The pledge is shared with your circle,** with a switch to turn it off. The design said communities, but those are public, and that would tell strangers what someone is quitting.
- **Badges are only visible to their owner,** because "Honest day" reveals a slip.
- **"Partnered up"** means someone is in your circle, because there's no partner feature yet.
- **Setup step 3 preselects My circle,** as in the design, and that becomes the starting audience for check-ins and posts. Without setup, check-ins start on Only me and posts on My circle.
- **Email links never show on the page,** even locally. The user removed this once real email worked.
- **The Cloudflare widget is hidden** (`data-appearance="interaction-only"`) unless Cloudflare wants a click. This removes the "For testing only" text the test keys show.

## 9. Demo

All demo accounts use the password `larping123`.

| Account | Shows |
| --- | --- |
| `maya` | Six days of check-ins with a slip, today left open, and a circle request from `sam` to accept live |
| `theo` | In `maya`'s circle, so sees their circle posts but not their private one. Has a report posted in two communities |
| `sam` | No circle, so only sees community posts |
| `jonas`, `priya` | A second circle. `priya` has a photo reflection |
| `lena` | Has a circle request waiting on `theo` |

The demo accounts are walled off because their password is public. They can't join real circles, write on real posts, or be changed or deleted, and real people can't register their usernames or an `@example.com` email. `flask clear-demo` then `flask seed-demo` refreshes them, and clearing also removes real people's comments on demo posts.

**Suggested flow:**
1. Ctrl+F5, then show the landing page and feed logged out.
2. Log in as `maya` and do today's check-in live.
3. Show Progress and the badges.
4. Press "I believe you" on a post.
5. Accept `sam`'s request.
6. Open `theo` in a private window to show `maya`'s circle post but not the private one.
7. Show days in character and "I broke character".
8. Write a post with a photo into two communities.

## 10. Rules the tests enforce

- `db.select(Post` must be followed by `visible_to`. It's the one rule for who sees a post, and hidden posts return 404.
- No raw SQL in `app/`. One-off table changes go in a throwaway script outside it.
- Every new route needs `@login_required`, or a deliberate entry in `PUBLIC_ENDPOINTS` in `tests/test_security.py`.
- No `style=` attributes, inline scripts or `|safe`, because the security policy blocks them. For per-element values, use classes, SVG attributes or `<progress>`.
- The tests refuse any database whose name doesn't end in `_test`.

Follow the "Adding a feature" checklist in `SECURITY.md` for anything new.

## 11. What's proven and what isn't

**Tests:** 147 pass: 121 across accounts, privacy and security, plus 26 for demo data. That last run of the three big files took 11 minutes, while the whole suite took about 100 seconds at 139 tests. Nobody has looked into why.

**Checked in a real (headless) browser:**
- "I believe you" not moving the page
- The Overall rule on the Write page's community boxes
- The password eye button
- A check-in shared with My circle, which only reached the ticked community and the circle
- A full sign-up with the hidden Cloudflare check, using test keys

**The user confirmed** real email confirmation works.

**Not proven yet:**
- Cloudflare with real keys. The test keys let everyone through, so the captcha isn't stopping any bots yet.
- The setup and pledge forms and the photo picker with a real mouse. The forms have automated tests only.
- The Render deploy, gunicorn in production, and rate limits behind Render's proxy.
- The GitHub checks. This machine has no `gh`, so their results weren't looked at. Look at the Actions tab on GitHub.

## 12. What's left

1. Commit and push (the user does this).
2. Trim the tests to about 50 by shrinking parametrized cases and removing overlap. Keep the login and CSRF route scans, the code scans, the audience checks, the demo wall and seed isolation, reset links working once, and the captcha failing closed.
3. Build more from the prototype if there's time. Still unbuilt: accountability partner and nudge, suggested people, notifications, saved report frequency, story carousel, larger-text setting. Their CSS was left out of `style.css`, so get `LARP-prototype.html` from the user first.
4. Rehearse the demo and confirm tables are final.
5. Deploy to Render, last:
   - Push, then in Render choose New > Blueprint.
   - Paste `EMAIL_WEBHOOK_URL` and real Turnstile keys. Those are a free widget in the Cloudflare dashboard, set up with the Render hostname.
   - Email links use the address Render provides (`RENDER_EXTERNAL_URL`), so there's nothing to set for those.
   - Render's free plan sleeps after 15 minutes and takes about a minute to wake, so open the site before presenting.
   - The free database expires 30 days after it's created and has no backups, so create it close to the hackathon.
   - Changing a table after deploying means recreating the hosted database.

## 13. Gaps we're choosing to ignore for the demo

- Can't edit or delete a post, or change your email.
- No moderation, reporting, blocking, two-factor login or backups, and photos aren't moderated.
- No pagination (50-post cap), and no user search beyond exact usernames.
- Day counts start when you join and can't be backdated.
- Register reveals taken emails, password login has no captcha, and setting a new password doesn't ask for the old one.
- Rate limits live in memory, so they reset on restart and only suit one server.
- Anyone can post as a demo account, because the password is public.
- Terms and privacy are drafts with no lawyer, which the user is fine with.
- Flask-Login's `utcnow` deprecation warning on Python 3.14 is harmless.
