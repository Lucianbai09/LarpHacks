# LarpHacks

Addiction tracker: post your progress and larp as someone who already quit, until it's true.

Flask, Jinja2 and PostgreSQL. Tested on Python 3.14 and PostgreSQL 18.

## Run it

In PowerShell, from the repo root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Prompts for your Postgres password.
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres larphacks

# Then fill in YOUR_PASSWORD and YOUR_SECRET_KEY in .env.
copy .env.example .env

.venv\Scripts\flask.exe init-db
.venv\Scripts\flask.exe seed-demo
```

That setup only happens once. Other `flask` commands below run the same way, through `.venv\Scripts\flask.exe`.

**To start the site from then on, press F5 in VS Code.** It runs `run.py` from whichever file you have open and opens http://127.0.0.1:5000 in your browser. Saved changes reload by themselves, and the red square in VS Code's toolbar stops the site.

Outside VS Code, run `.venv\Scripts\python.exe run.py`.

## Demo accounts

`flask seed-demo` is optional and adds three accounts, all with the password `larping123`. Anyone can log in to them because the password is public, so only use them for fake data. Their passwords can't be changed and they can't be deleted, so one visitor can't break the demo for everyone else.

| Account | Shows |
| --- | --- |
| `maya` | Has a post for each audience, and a circle request from `sam` waiting |
| `theo` | In `maya`'s circle, so they can read `maya`'s circle posts but not the private one |
| `sam` | Not in a circle yet, so they only see community posts |

## Accounts and email

There's one email flow: a signed link that works once and expires in an hour. It confirms new accounts, logs people in without a password, and is how people reset a password. An account only exists once its link is clicked, so bots that can't receive email leave nothing behind.

Passwords are optional, set from the account page, with a 6-character minimum. Register, log in and email links are rate limited per IP address.

**Locally, you don't need an email account.** With `BREVO_API_KEY` blank, F5 shows each link on the page instead of sending it. This only happens in debug mode, so never on Render.

**To send real email:**

1. Sign up at [brevo.com](https://www.brevo.com). The free plan sends 300 emails a day.
2. Add and verify a sender address in Brevo. Emails from a domain you own are less likely to land in spam than ones from a Gmail address.
3. Create an API key in Brevo.
4. Put the key in `BREVO_API_KEY` and the sender address in `EMAIL_FROM`, in `.env` locally and in the environment settings on Render.

If emails don't arrive, check the logs. If Brevo reports an unrecognised IP address, turn off IP blocking in its security settings, because Render's addresses change.

To switch provider, change `deliver()` in `app/mail.py`. It uses a web API because Render's free plan blocks SMTP.

## Terms and privacy

`/terms` and `/privacy` are starting drafts written without a lawyer. They describe what the site actually does, so update them when that changes, and get them reviewed before real people rely on them. When they change, update `TERMS_VERSION` in `app/models.py`.

## Who can see a post

| Audience | Who can read it |
| --- | --- |
| Community | Anyone, including people without an account |
| My circle | The author and people in their circle |
| Only me | The author |

Circle membership is mutual and needs an accepted request. Communities on a profile are only shown to that person and their circle.

`visible_to()` in `app/models.py` is the one place these rules live. Any new query that reads posts must use it.

## Layout

| Path | What's there |
| --- | --- |
| `run.py` | Starts the site locally, and is what gunicorn loads on Render |
| `render.yaml` | Render's setup: the web service and its database |
| `app/__init__.py` | App factory and the `flask` commands |
| `app/models.py` | Tables, the category seed list, and `visible_to()` |
| `app/auth.py` | Register, log in, email links, account page |
| `app/mail.py` | Sends email |
| `app/views.py` | Feeds, write, posts, communities, profiles, circles |
| `app/demo.py` | Demo data for `flask seed-demo` |
| `app/templates/` | Jinja templates. `_post.html` is one post, `_forms.html` has the one-click button macro |
| `app/static/style.css` | All the styling |

## Changing things

**Add a category:** add a line to `CATEGORIES` in `app/models.py`, then run `flask init-db`. Pages pick it up from the database.

**Change a table:** there are no migrations yet. `flask init-db` only creates missing tables, so changing an existing one means recreating your local database with `dropdb` and `createdb`, then running `flask init-db` again. On Render, that means deleting and recreating the database, which loses its data.

## Deploy on Render

1. Push the repo to GitHub. `.env` stays out of git, so your local password doesn't go with it.
2. In the Render dashboard, choose **New > Blueprint**, pick the repo, and apply it. Enter your Brevo details when it asks. Without them, nobody can register or use email links, but password logins still work.

`render.yaml` creates the site and its Postgres database, generates `SECRET_KEY`, and connects them. New tables, categories and the demo accounts are added each time the site starts. Before real people use the site, remove `flask seed-demo` from `startCommand` and delete the demo accounts.

On the free plan:

- The site sleeps after 15 minutes without visitors and takes about a minute to wake, so open it before you demo.
- The database expires 30 days after it's created, has no backups, and you only get one free database per workspace.
