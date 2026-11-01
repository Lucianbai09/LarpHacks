# Cove

Hackathon addiction tracker. The product is called Cove, while the repo and databases keep the name LarpHacks. Flask, Jinja2, PostgreSQL, deployed on Render. See `README.md` for setup, and read `HANDOFF.md` first for the rubric, what's built, decisions already made and what's left.

## Rules for every change

- Work like a lazy senior dev: do the simplest thing that works for the demo, and don't over-engineer or over-test.
- Follow the checklist under "Adding a feature" in `SECURITY.md`. Add one or two tests for what matters, not exhaustive ones. The team wants about 50 tests in total.
- Run the tests related to a change before calling it done. They use `TEST_DATABASE_URL`, whose name must end in `_test`, because they wipe it.
- Never edit `larphacks` by hand without checking it only holds demo data. There are no migrations.
- Secrets only go in `.env`, which git ignores.

## Working with the team

The team avoids the terminal, so lead with what they can click: F5 runs the site, and the Testing panel runs the tests.
