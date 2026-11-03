"""Login, logout, CSRF protection, lock, password change."""

import re

import pytest

import auth
import db
from conftest import PASSWORD, USERNAME


def csrf(client, path="/login"):
    """Fetches the CSRF token from a page."""
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def log_in(client, password=PASSWORD, username=USERNAME, **extra):
    return client.post("/login", data={"benutzername": username, "passwort": password,
                                       "csrf_token": csrf(client), **extra})


def test_all_pages_protected(anon):
    for path in ["/", "/monat/2026-10", "/wiederkehrend", "/buchung/1", "/serie/1/0", "/passwort"]:
        r = anon.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"], path
    r = anon.post("/buchung", data={"typ": "ausgabe", "datum": "2026-10-01",
                                     "beschreibung": "X", "betrag": "1"})
    assert r.status_code in (302, 400)
    with db.connect() as conn:
        assert db.all_transactions(conn, 1) == []
    assert anon.get("/static/style.css").status_code == 200


def test_login_and_redirect(anon):
    r = anon.get("/monat/2027-03")
    assert "weiter=/monat/2027-03" in r.headers["Location"]
    token = csrf(anon)
    r = anon.post("/login?weiter=/monat/2027-03",
                  data={"benutzername": USERNAME, "passwort": PASSWORD, "csrf_token": token})
    assert r.headers["Location"] == "/monat/2027-03"
    assert "März 2027" in anon.get("/monat/2027-03").get_data(as_text=True)


def test_no_redirect_to_foreign_sites(anon):
    token = csrf(anon)
    for target in ["//boese.de", "https://boese.de", "/\\boese.de"]:
        r = anon.post(f"/login?weiter={target}",
                      data={"benutzername": USERNAME, "passwort": PASSWORD, "csrf_token": token})
        assert r.headers["Location"] == "/", target
        anon.post("/logout", data={"csrf_token": csrf(anon, "/monat/2026-10")})
        token = csrf(anon)


def test_wrong_password(anon):
    r = log_in(anon, password="falsch")
    assert r.status_code == 401
    assert "Benutzername oder Passwort ist falsch" in r.get_data(as_text=True)
    assert log_in(anon, username="unbekannt").status_code == 401
    assert anon.get("/").status_code == 302


def test_lock_after_failed_attempts(anon):
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        assert log_in(anon, password="falsch").status_code == 401
    r = log_in(anon)  # even the correct password is rejected now
    assert r.status_code == 429
    assert "Zu viele Fehlversuche" in r.get_data(as_text=True)
    with db.connect() as conn:
        db.clear_failures(conn)  # like set_password.py
    assert log_in(anon).status_code == 302


def test_csrf_required(anon):
    r = anon.post("/login", data={"benutzername": USERNAME, "passwort": PASSWORD})
    assert r.status_code == 400
    assert log_in(anon).status_code == 302
    # Logged in, but form without/with a wrong token
    form = {"typ": "ausgabe", "datum": "2026-10-01", "beschreibung": "X", "betrag": "1"}
    assert anon.post("/buchung", data=form).status_code == 400
    assert anon.post("/buchung", data={**form, "csrf_token": "falsch"}).status_code == 400
    assert anon.post("/buchung", data={**form, "csrf_token": csrf(anon, "/monat/2026-10")}).status_code == 302
    with db.connect() as conn:
        assert len(db.all_transactions(conn, 1)) == 1


def test_logout(anon):
    log_in(anon)
    assert anon.get("/monat/2026-10").status_code == 200
    anon.post("/logout", data={"csrf_token": csrf(anon, "/monat/2026-10")})
    assert anon.get("/monat/2026-10").status_code == 302


def test_remember_me(anon):
    r = log_in(anon, angemeldet_bleiben="1")
    assert "Expires=" in r.headers["Set-Cookie"]
    anon.post("/logout", data={"csrf_token": csrf(anon, "/monat/2026-10")})
    r = log_in(anon)
    assert "Expires=" not in r.headers["Set-Cookie"]  # ends with the browser


def test_cookie_settings(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"]
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_change_password_logs_out_other_devices(app):
    phone, laptop = app.test_client(), app.test_client()
    log_in(phone)
    log_in(laptop)

    token = csrf(laptop, "/passwort")
    r = laptop.post("/passwort", data={"alt": "falsch", "neu": "neues-passwort-123",
                                       "neu2": "neues-passwort-123", "csrf_token": token},
                    follow_redirects=True)
    assert "bisherige Passwort ist falsch" in r.get_data(as_text=True)
    r = laptop.post("/passwort", data={"alt": PASSWORD, "neu": "kurz", "neu2": "kurz",
                                       "csrf_token": token}, follow_redirects=True)
    assert "mindestens" in r.get_data(as_text=True)

    r = laptop.post("/passwort", data={"alt": PASSWORD, "neu": "neues-passwort-123",
                                       "neu2": "neues-passwort-123", "csrf_token": token})
    assert r.status_code == 302
    assert laptop.get("/monat/2026-10").status_code == 200   # stays logged in
    assert phone.get("/monat/2026-10").status_code == 302    # logged out

    assert log_in(phone).status_code == 401
    assert log_in(phone, password="neues-passwort-123").status_code == 302


def test_password_only_stored_as_hash(app):
    with db.connect() as conn:
        stored = db.get_user_by_name(conn, USERNAME)["passwort_hash"]
    assert PASSWORD not in stored
    assert stored.startswith(("scrypt:", "pbkdf2:"))


def test_hint_without_account(app):
    with db.connect() as conn:
        conn.execute("DELETE FROM users")
        conn.commit()
    html = app.test_client().get("/login").get_data(as_text=True)
    assert "set_password.py" in html


def test_check_new_password():
    with pytest.raises(ValueError):
        auth.check_new_password("kurz", "kurz")
    with pytest.raises(ValueError):
        auth.check_new_password("langes-passwort-1", "langes-passwort-2")
    auth.check_new_password("langes-passwort-1", "langes-passwort-1")


def test_set_password_without_terminal(app, monkeypatch, capsys):
    """Like in PyCharm's Run window: no TTY -> normal input instead of getpass."""
    import getpass
    import io
    import set_password

    monkeypatch.setattr("sys.stdin", io.StringIO("neuer-name\nanderes-passwort-9\nanderes-passwort-9\n"))
    monkeypatch.setattr(getpass, "getpass", lambda *a, **k: pytest.fail("getpass must not run without a terminal"))
    assert set_password.main() == 0
    assert "Saved" in capsys.readouterr().out

    c = app.test_client()
    assert log_in(c, username="neuer-name", password="anderes-passwort-9").status_code == 302


def test_set_password_too_short(app, monkeypatch, capsys):
    import io
    import set_password

    monkeypatch.setattr("sys.stdin", io.StringIO("\nkurz\nkurz\n"))
    assert set_password.main() == 1
    assert "mindestens" in capsys.readouterr().out


def test_pwa_files_public(anon):
    """Service worker, manifest and offline page must load without login (installable app)."""
    import json
    sw = anon.get("/sw.js")
    assert sw.status_code == 200 and sw.mimetype == "text/javascript"
    assert sw.headers["Cache-Control"] == "no-cache"
    assert "OFFLINE_PAGE" in sw.get_data(as_text=True)

    manifest = anon.get("/manifest.webmanifest")
    assert manifest.status_code == 200 and manifest.mimetype == "application/manifest+json"
    data = json.loads(manifest.get_data(as_text=True))
    assert data["display"] == "standalone" and data["start_url"] == "/"
    for icon in data["icons"]:
        assert anon.get(icon["src"]).status_code == 200

    assert anon.get("/static/offline.html").status_code == 200
    login = anon.get("/login").get_data(as_text=True)
    assert 'rel="manifest" href="/manifest.webmanifest"' in login
    assert 'navigator.serviceWorker.register("/sw.js")' in login
