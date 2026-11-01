from app import create_app
from app.models import init_db

app = create_app()

if __name__ == "__main__":
    # Local runs pick up new tables and categories by themselves. Render runs `flask init-db` instead.
    with app.app_context():
        init_db()
    # Saving .env restarts the site too, so new settings apply straight away.
    app.run(debug=True, extra_files=[".env"])
