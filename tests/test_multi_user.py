"""Multiple accounts: data separation, lock per account, demo account, migration of old databases."""

from datetime import date

import pytest

import auth
import db
import finance as fin
import reset_demo
from conftest import PASSWORD, USERNAME

ANNA, ANNA_PASSWORD = "anna", "annas-geheimes-passwort"


@pytest.fixture
def two_users(app):
    """Two logged-in browsers: eugen (account 1) and anna (account 2); CSRF check off."""
    with db.connect() as conn:
        db.set_user(conn, ANNA, auth.hash_password(ANNA_PASSWORD))
    app.config["CSRF_ENABLED"] = False
    eugen, anna = app.test_client(), app.test_client()
    assert eugen.post("/login", data={"benutzername": USERNAME, "passwort": PASSWORD}).status_code == 302
    assert anna.post("/login", data={"benutzername": ANNA, "passwort": ANNA_PASSWORD}).status_code == 302
    return eugen, anna


def test_everyone_sees_only_own_transactions(two_users):
    eugen, anna = two_users
    eugen.post("/buchung", data={"typ": "ausgabe", "datum": "2026-10-15",
                                 "beschreibung": "Geheimer Einkauf", "betrag": "50"})
    eugen.post("/wiederkehrend", data={"typ": "einnahme", "beschreibung": "Geheimes Gehalt",
                                       "betrag": "3000", "intervall_monate": "1",
                                       "start_datum": "2026-10-01", "end_datum": ""})
    anna.post("/buchung", data={"typ": "ausgabe", "datum": "2026-10-20",
                                "beschreibung": "Annas Einkauf", "betrag": "10"})

    october_anna = anna.get("/monat/2026-10").get_data(as_text=True)
    assert "Annas Einkauf" in october_anna
    assert "Geheim" not in october_anna
    assert "Geheim" not in anna.get("/wiederkehrend").get_data(as_text=True)
    assert "Annas" not in eugen.get("/monat/2026-10").get_data(as_text=True)


def test_no_access_to_foreign_ids(two_users):
    eugen, anna = two_users
    eugen.post("/buchung", data={"typ": "ausgabe", "datum": "2026-10-15",
                                 "beschreibung": "Einkauf", "betrag": "50"})
    eugen.post("/wiederkehrend", data={"typ": "ausgabe", "beschreibung": "Miete", "betrag": "900",
                                       "intervall_monate": "1", "start_datum": "2026-10-01",
                                       "end_datum": "2027-03-31"})
    form = {"typ": "ausgabe", "datum": "2026-10-15", "beschreibung": "Gehackt", "betrag": "1"}

    assert anna.get("/buchung/1").status_code == 404
    assert anna.post("/buchung/1", data=form).status_code == 404
    assert anna.post("/buchung/1/loeschen").status_code == 404
    assert anna.get("/serie/1/0").status_code == 404
    assert anna.post("/serie/1/0", data={**form, "umfang": "alle"}).status_code == 404
    assert anna.post("/serie/1/0", data={"umfang": "alle", "aktion": "loeschen"}).status_code == 404
    assert anna.post("/wiederkehrend/1/beenden", data={"end_datum": "2026-10-31"}).status_code == 404
    assert anna.post("/wiederkehrend/1/loeschen").status_code == 404
    assert anna.post("/verschieben", data={"art": "buchung", "id": "1", "datum": "2026-10-20"}).status_code == 404
    assert anna.post("/verschieben", data={"art": "serie", "id": "1", "nummer": "0",
                                           "datum": "2026-10-20"}).status_code == 404

    with db.connect() as conn:
        assert [t["beschreibung"] for t in db.all_transactions(conn, 1)] == ["Einkauf"]
        series = db.get_recurring(conn, 1, 1)
        assert series["beschreibung"] == "Miete" and series["end_datum"] == "2027-03-31"


def test_split_series_stays_with_owner(two_users):
    eugen, anna = two_users
    anna.post("/wiederkehrend", data={"typ": "ausgabe", "beschreibung": "Miete", "betrag": "900",
                                      "intervall_monate": "1", "start_datum": "2026-10-01",
                                      "end_datum": "2027-03-31"})
    anna.post("/serie/1/2", data={"typ": "ausgabe", "datum": "2026-12-01", "beschreibung": "Miete neu",
                                  "betrag": "950", "umfang": "ab"})
    with db.connect() as conn:
        assert len(db.all_recurring(conn, 2)) == 2
        assert db.all_recurring(conn, 1) == []
    assert "Miete" not in eugen.get("/monat/2027-01").get_data(as_text=True)


def test_lock_applies_to_one_account_only(two_users, app):
    stranger = app.test_client()
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        assert stranger.post("/login", data={"benutzername": ANNA, "passwort": "falsch"}).status_code == 401
    assert stranger.post("/login", data={"benutzername": ANNA, "passwort": ANNA_PASSWORD}).status_code == 429
    # eugen can still log in
    fresh = app.test_client()
    assert fresh.post("/login", data={"benutzername": USERNAME, "passwort": PASSWORD}).status_code == 302


@pytest.fixture
def demo(app):
    """Logged-in browser in the demo account; CSRF check off."""
    with db.connect() as conn:
        reset_demo.reset(conn)
    app.config["CSRF_ENABLED"] = False
    c = app.test_client()
    r = c.post("/login", data={"benutzername": auth.DEMO_USERNAME, "passwort": auth.DEMO_PASSWORD})
    assert r.status_code == 302
    return c


def test_demo_credentials_on_login_page(app):
    assert "Zum Ausprobieren" not in app.test_client().get("/login").get_data(as_text=True)
    with db.connect() as conn:
        reset_demo.reset(conn)
    html = app.test_client().get("/login").get_data(as_text=True)
    assert auth.DEMO_USERNAME in html and auth.DEMO_PASSWORD in html


def test_demo_cannot_change_password(demo):
    page = demo.get("/monat/2026-10").get_data(as_text=True)
    assert "Demo-Zugang" in page
    assert "/passwort" not in page
    assert demo.get("/passwort").status_code == 403
    r = demo.post("/passwort", data={"alt": auth.DEMO_PASSWORD, "neu": "uebernommen-123",
                                     "neu2": "uebernommen-123"})
    assert r.status_code == 403


def test_reset_demo(demo):
    demo.post("/buchung", data={"typ": "ausgabe", "datum": date.today().isoformat(),
                                "beschreibung": "Unsinn vom Besucher", "betrag": "999"})
    with db.connect() as conn:
        db.add_transaction(conn, 1, "2026-10-01", "Eigene Buchung", "", 100, "ausgabe")
        uid = reset_demo.reset(conn)
        demo_descriptions = [t["beschreibung"] for t in db.all_transactions(conn, uid)]
        assert "Unsinn vom Besucher" not in demo_descriptions
        assert "Wocheneinkauf" in demo_descriptions
        assert len(db.all_recurring(conn, uid)) == 5
        assert [t["beschreibung"] for t in db.all_transactions(conn, 1)] == ["Eigene Buchung"]
    # Password unchanged -> demo session stays logged in, sample data visible
    page = demo.get(f"/monat/{fin.current_month()}").get_data(as_text=True)
    assert "Wocheneinkauf" in page and "Unsinn" not in page


def test_demo_does_not_overwrite_real_account(app):
    with db.connect() as conn:
        db.set_user(conn, auth.DEMO_USERNAME, auth.hash_password("echtes-passwort-1"))
        with pytest.raises(RuntimeError):
            reset_demo.reset(conn)


def test_migration_single_account(tmp_path):
    """Database from the time with exactly one account: afterwards everything belongs to account 1."""
    path = tmp_path / "single.db"
    with db.connect(path) as c:
        c.executescript("""
            CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, datum TEXT NOT NULL,
                beschreibung TEXT NOT NULL, kategorie TEXT NOT NULL DEFAULT '',
                betrag_cent INTEGER NOT NULL, typ TEXT NOT NULL);
            CREATE TABLE recurring (id INTEGER PRIMARY KEY AUTOINCREMENT, beschreibung TEXT NOT NULL,
                kategorie TEXT NOT NULL DEFAULT '', betrag_cent INTEGER NOT NULL, typ TEXT NOT NULL,
                intervall_monate INTEGER NOT NULL DEFAULT 1, tag INTEGER NOT NULL DEFAULT 1,
                start_datum TEXT NOT NULL, end_datum TEXT);
            CREATE TABLE users (id INTEGER PRIMARY KEY CHECK (id = 1), benutzername TEXT NOT NULL,
                passwort_hash TEXT NOT NULL);
            CREATE TABLE login_fehlversuche (zeit REAL NOT NULL);
            INSERT INTO transactions (datum, beschreibung, betrag_cent, typ)
                VALUES ('2026-10-01', 'Alt', 100, 'ausgabe');
            INSERT INTO recurring (beschreibung, betrag_cent, typ, start_datum)
                VALUES ('Miete', 90000, 'ausgabe', '2026-10-01');
            INSERT INTO users VALUES (1, 'eugen', 'hash');
            INSERT INTO login_fehlversuche VALUES (1.0);
        """)
    db.init_db(path)
    db.init_db(path)  # a second start changes nothing
    with db.connect(path) as c:
        assert db.get_user(c, 1)["benutzername"] == "eugen"
        assert [t["beschreibung"] for t in db.all_transactions(c, 1)] == ["Alt"]
        assert [r["beschreibung"] for r in db.all_recurring(c, 1)] == ["Miete"]
        assert db.set_user(c, "anna", "hash2") == 2
        assert db.all_transactions(c, 2) == []
