import pytest

import auth
import db

USERNAME = "eugen"
PASSWORD = "sehr-geheimes-passwort"


@pytest.fixture
def app(tmp_path, monkeypatch):
    """App with an empty test database and one user account."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    import main
    db.init_db()
    with db.connect() as conn:
        db.set_user(conn, USERNAME, auth.hash_password(PASSWORD))
    main.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False, CSRF_ENABLED=True)
    return main.app


@pytest.fixture
def anon(app):
    """Browser that is not logged in, CSRF check active."""
    return app.test_client()


@pytest.fixture
def client(app):
    """Logged-in browser; CSRF check off so the functional tests stay lean."""
    app.config["CSRF_ENABLED"] = False
    c = app.test_client()
    r = c.post("/login", data={"benutzername": USERNAME, "passwort": PASSWORD})
    assert r.status_code == 302
    return c
