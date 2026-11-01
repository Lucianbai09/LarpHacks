# Security

## What's in place

| Risk | Protection | Where |
| --- | --- | --- |
| SQL injection | Every query goes through SQLAlchemy with bound parameters. There's no raw SQL. | `tests/test_security.py` fails on raw SQL |
| Cross-site scripting | Templates escape everything, and a Content Security Policy blocks inline scripts. | `app/security.py` |
| Forged form submissions | CSRF tokens on every POST, plus SameSite cookies. | `app/__init__.py` |
| Bots | Cloudflare Turnstile captcha on register and forgot password. | `app/security.py` |
| Password guessing and spam | Per-IP rate limits. Everything that changes data is limited by default, including new routes. | `app/__init__.py`, `app/auth.py` |
| Stolen passwords | Hashed with scrypt. Changing a password logs out every other device. | `app/models.py` |
| Account takeover | Password reset is a signed emailed link that works once and expires in an hour. Links are built from a fixed URL, so a faked Host header can't redirect them. | `app/auth.py` |
| Reading private posts | `visible_to()` is the only rule for who can see a post, and it covers its photo. Posts you can't see return a 404. | `app/models.py` |
| Reading check-ins | Check-ins and the Progress page only ever read your own rows. Sharing one makes a normal post that goes through `visible_to()`. | `app/views.py` |
| Malicious uploads | Every photo is redrawn as a small JPEG, so it can't carry a script or the GPS location phones add. Anything else is refused. | `app/photos.py` |
| Revealing who has an account | Forgot password responds the same way for every email, and emails never mention what someone is quitting. | `app/auth.py`, `app/mail.py` |
| Public demo passwords | Demo accounts can't join real circles or write on real people's posts, and can't be changed or deleted. | `is_demo`, `app/views.py` |
| Clickjacking, HTTPS downgrades | `X-Frame-Options`, `frame-ancestors` and HSTS headers. | `app/security.py` |
| Oversized requests, DDoS | An 11 MB request limit, length limits on posts, and a stricter rate limit on writing posts. Render puts Cloudflare's DDoS protection in front of every site. | `app/__init__.py` |

## Adding a feature

Go through this for every new feature:

1. **Reading posts?** Filter with `visible_to(current_user)`. Never query `Post` without it.
2. **New route?** Add `@login_required`, unless it's truly public, in which case add it to `PUBLIC_ENDPOINTS` in `tests/test_security.py`.
3. **Acting on something by ID?** Check that the current user is allowed to, as `get_writable_post()` does.
4. **New form?** Include the CSRF token, and validate and length-limit every field on the server.
5. **Sends email or could be abused?** Add a stricter `@limiter.limit`, and a captcha if logged-out visitors can reach it.
6. **New table with user data?** Use `ondelete="CASCADE"` on its user foreign key so deleting an account removes it, and update the privacy page.
7. **Showing user content?** Let Jinja escape it. Never use `|safe`, `Markup()`, inline scripts or `style=` attributes. The security policy blocks the last two, so `style=` silently does nothing. Use a class instead.
8. **Demo accounts?** Make sure they still can't reach real people's data, because their passwords are public.
9. **Add tests,** including one that proves the wrong person gets refused.

## What runs automatically

Once this is on GitHub, nobody has to remember these:

- **On every push and every Monday:** `.github/workflows/security.yml` runs all the tests, checks dependencies for known vulnerabilities with `pip-audit`, scans the code with `bandit`, and starts the site with gunicorn as Render does. GitHub emails you if any of it fails.
- **Every week:** Dependabot opens a pull request for each outdated dependency, and the checks above run on it.
- **On every run:** `tests/test_security.py` scans the whole app, so a new route without login or CSRF protection, or any raw SQL, fails the checks.

## Known limits

These are fine for a hackathon demo, and worth fixing before real people rely on the site:

- **There are no password rules,** on purpose. Any password that isn't blank works, so rate limits are the only thing slowing down guessing.
- **Photos aren't moderated.** Anyone with an account can post any picture, including publicly, and the demo accounts' password is public. There's no way to report or remove one except in the database.
- **Email confirmation doesn't block anything.** Unconfirmed accounts work normally and just don't get the checkmark, so the captcha and rate limits are what stop bots.
- **Register reveals taken emails,** because it says when an email already has an account.
- **Password login has no captcha,** only rate limits, so a demo can't get stuck on it.
- **Rate limit counts live in memory.** They reset when the site restarts and only work with one server.
- **There's no two-factor login, moderation tooling or database backups.**
- **The terms and privacy pages** are drafts written without a lawyer.
