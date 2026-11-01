import re

PASSWORD = "secret1"


class Browser:
    """One visitor, with their own cookies. Goes through CSRF like a real browser does."""

    def __init__(self, app):
        self.app = app
        self.c = app.test_client()

    def token(self, path):
        html = self.c.get(path, follow_redirects=True).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def post(self, path, data=None, token_from="/login", **kwargs):
        data = dict(data or {})
        data.setdefault("csrf_token", self.token(token_from))
        return self.c.post(path, data=data, **kwargs)

    def text(self, path):
        return self.c.get(path).get_data(as_text=True)

    def logged_in(self):
        return self.c.get("/write").status_code == 200

    def register(self, username, email=None, password=PASSWORD, terms=True, **extra):
        data = {"username": username, "email": f"{username}@mail.test" if email is None else email, "password": password, **extra}
        if terms:
            data["terms"] = "on"
        return self.post("/register", data, token_from="/register")

    def login(self, identifier, password=PASSWORD, path="/login"):
        return self.post(path, {"identifier": identifier, "password": password}, token_from="/login")

    def logout(self):
        return self.post("/logout")

    def write(self, body, visibility="public", category="alcohol", report_type="daily"):
        return self.post("/write", {"body": body, "visibility": visibility, "category": category, "report_type": report_type})

    def add(self, username):
        return self.post("/circle/add", {"username": username}, follow_redirects=True)

    def remove(self, username):
        return self.post("/circle/remove", {"username": username})

    def set_password(self, password):
        return self.post("/account/password", {"password": password}, follow_redirects=True)
