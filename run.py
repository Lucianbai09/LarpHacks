from app import create_app

app = create_app()

if __name__ == "__main__":
    # Saving .env restarts the site too, so new settings apply straight away.
    app.run(debug=True, extra_files=[".env"])
