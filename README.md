# Cove

Addiction tracker, made at LarpHacks: post your progress and larp as someone who already quit, until it's true.

Flask, Jinja2 and PostgreSQL. Tested on Python 3.14 and PostgreSQL 18.

## Run it

In PowerShell, from the repo root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# Each prompts for your Postgres password. The second is only used by the tests.
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres larphacks
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres larphacks_test

# Then fill in YOUR_PASSWORD and YOUR_SECRET_KEY in .env.
copy .env.example .env

.venv\Scripts\flask.exe init-db
.venv\Scripts\flask.exe seed-demo
```

That setup only happens once. Other `flask` commands below run the same way, through `.venv\Scripts\flask.exe`.

**To start the site from then on, press F5 in VS Code.** It runs `run.py` from whichever file you have open and opens http://127.0.0.1:5000 in your browser. Saved changes reload by themselves, and the red square in VS Code's toolbar stops the site.

If the site ever stops responding after an error, VS Code's debugger may have paused it, so press the red square and then F5. For a live demo, use **Ctrl+F5**, which runs without the debugger.

Outside VS Code, run `.venv\Scripts\python.exe run.py`.

## Demo accounts

`flask seed-demo` is optional and adds six accounts with made-up posts, all with the password `larping123`.

| Account | Shows |
| --- | --- |
| `maya` | Has a post for each audience, a week of check-ins with today's still open to do live, and a circle request from `sam` to accept live |
| `theo` | In `maya`'s circle, so they can read `maya`'s circle posts but not the private one |
| `sam` | Not in a circle yet, so they only see community posts |
| `jonas`, `priya` | A second circle, with their own circle and private posts |
| `lena` | Has a circle request waiting on `theo` |

**Demo data can't affect real people.** The password is public, so demo accounts are walled off:

- They're labelled "demo" everywhere, and marked `is_demo` in the database.
- They can't join a real person's circle, comment on or react to real posts, or change their own password or delete themselves.
- Seeding only ever adds demo rows, does nothing if they're already there, and refuses to run if a real account has one of their usernames.
- `flask clear-demo` deletes demo accounts and everything attached to them, including real people's comments on demo posts. Real accounts, posts and circles stay.

Real people can't register those usernames or an `@example.com` email.

## Accounts and email

Registering takes a username, an email and a password, and each email can only have one account. There are no password rules, so anything that isn't blank works. Accounts work straight away. A confirmation link is emailed too, and clicking it adds a checkmark next to your name. Forgot password emails a link that works once and expires in an hour.

**Without email set up,** accounts still work, but no links get sent, so nobody can confirm an email or reset a password. The error shows in VS Code's Debug Console.

**To send real email for free,** use a small Google Apps Script that sends from a Gmail account. It handles 100 emails a day, needs no card or domain, and works on Render, whose free plan blocks SMTP. Recipients see that Gmail address as the sender, so you may want a team one.

1. Signed in to that Gmail account, go to [script.google.com](https://script.google.com) and create a new project.
2. Replace everything in the editor with this, then save:

   ```js
   function doPost(e) {
     const email = JSON.parse(e.postData.contents);
     MailApp.sendEmail({ to: email.to, subject: email.subject, body: email.body, name: "Cove" });
     return ContentService.createTextOutput("sent");
   }
   ```

3. Choose **Deploy > New deployment**, click the gear icon, and pick **Web app**.
4. Set **Execute as** to **Me** and **Who has access** to **Anyone**, then click **Deploy**.
5. Approve the permissions. Google warns that the app is unverified because it's your own script, so choose **Advanced**, then go to the project and allow it.
6. Back in the editor, pick `doPost` in the function dropdown and click **Run**, approving anything it asks. A red error about `postData` is expected. Skipping this can leave the script answering every request with a 403 "You need access" page.
7. Copy the **Web app URL** and paste it after `EMAIL_WEBHOOK_URL=` in `.env`, then save. The site restarts by itself.

To check it, open the URL in a private browser window. `Script function not found: doGet` means it's working, because the script only handles POST requests.

Treat that URL like a password, because anyone who has it can send email from that account.

If emails don't arrive, check spam, then look for an error in VS Code's Debug Console. To switch provider, change `deliver()` in `app/mail.py`.

## Security

`SECURITY.md` lists what's protected, what runs automatically, and the checklist for every new feature.

**Captcha:** locally, `.env` uses Cloudflare's public test keys, which always pass, so they don't stop any bots. The widget stays hidden unless Cloudflare wants someone to click it. For the real thing, add a free Turnstile widget in the [Cloudflare dashboard](https://dash.cloudflare.com/?to=/:account/turnstile) with your Render hostname, and put its keys in Render's environment settings. With no keys set, the captcha is off.

**Tests:** in VS Code, open the **Testing** panel (the flask icon) and click **Run Tests**. They run against the separate `larphacks_test` database and wipe it each time, so create that once with `createdb` as above.

## Terms and privacy

`/terms` and `/privacy` are simple drafts for the hackathon demo, written without a lawyer. They describe what the site does, so update them if that changes, along with `TERMS_VERSION` in `app/models.py`.

## Who can see a post

| Audience | Who can read it |
| --- | --- |
| Community | Anyone, including people without an account |
| My circle | The author and people in their circle |
| Only me | The author |

Circle membership is mutual and needs an accepted request. Communities on a profile are only shown to that person and their circle. A post's photo has the same audience as the post.

A post goes into any number of communities, or into Overall on its own. Daily check-ins and the Progress page are only visible to you. Sharing a check-in turns a one-line summary of it into a normal post, in the communities you ticked as staying in character for, or Overall if you ticked none.

Your pledge is visible to you and your circle, unless you turn that off. Achievement badges are only visible to you.

`visible_to()` in `app/models.py` is the one place these rules live. Any new query that reads posts must use it.

## Layout

| Path | What's there |
| --- | --- |
| `run.py` | Starts the site locally, and is what gunicorn loads on Render |
| `render.yaml` | Render's setup: the web service and its database |
| `app/__init__.py` | App factory and the `flask` commands |
| `app/models.py` | Tables, the category seed list, and `visible_to()` |
| `app/auth.py` | Register, log in, email confirmation, password reset, account page |
| `app/security.py` | Captcha, password rules, security headers |
| `app/mail.py` | Sends email |
| `tests/` | Automated tests, including rules every new route must follow |
| `.github/` | Weekly security checks and dependency updates |
| `app/views.py` | Feeds, write, check-ins, progress, posts, communities, profiles, circles |
| `app/photos.py` | Cleans up uploaded photos |
| `app/badges.py` | The achievement badges and what earns each one |
| `app/demo.py` | Demo data for `flask seed-demo` |
| `app/templates/` | Jinja templates. `_post.html` is one post, `_forms.html` has the form macros, `_ui.html` has icons and medals, `_icons.html` is the icon set |
| `app/static/style.css` | All the styling, and the design system's colours at the top |
| `app/static/app.js` | Confirm pop-ups, the password eye button, and the landing page's motion |

## Changing things

**Add a category:** add a line to `CATEGORIES` in `app/models.py`, with an icon name from `_icons.html`, then run `flask init-db`. Pages pick it up from the database.

**Change the check-in questions:** they're in `app/templates/check_in.html`, and the 1 to 10 scale is at the top of `app/models.py`.

**Add a badge:** add it to `ACHIEVEMENTS` in `app/badges.py`, and its rule to `qualifying_badges()`. If it's earned by something other than a form submitted to `app/views.py`, call `award_badges()` there too.

**Change a table:** there are no migrations yet. `flask init-db` only creates missing tables, so changing an existing one means recreating your local database with `dropdb` and `createdb`, then running `flask init-db` again. On Render, that means deleting and recreating the database, which loses its data.

## Deploy on Render

Do this once the tables are final, because there are no migrations.

1. Push the repo to GitHub. `.env` stays out of git, so your local password doesn't go with it.
2. In the Render dashboard, choose **New > Blueprint**, pick the repo, and apply it. Paste your email script URL and Turnstile keys when it asks. Without the email URL, confirmation and password reset emails don't send. Without the keys, the captcha is off. Everything else still works.

`render.yaml` creates the site and its Postgres database, generates `SECRET_KEY`, and connects them. New tables, categories and the demo accounts are added each time the site starts. Before real people use the site, remove `flask seed-demo` from `startCommand` and delete the demo accounts.

On the free plan:

- The site sleeps after 15 minutes without visitors and takes about a minute to wake, so open it before you demo.
- The database expires 30 days after it's created, has no backups, and you only get one free database per workspace.
