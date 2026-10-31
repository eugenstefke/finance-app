"""SQLite access of the finance app."""

import calendar
import sqlite3
from pathlib import Path

from flask import g

import finance as fin

DB_PATH = Path(__file__).with_name("finanzen.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL DEFAULT 1,    -- owner (users.id)
    datum         TEXT    NOT NULL,              -- YYYY-MM-DD
    beschreibung  TEXT    NOT NULL,
    kategorie     TEXT    NOT NULL DEFAULT '',
    betrag_cent   INTEGER NOT NULL CHECK (betrag_cent > 0),
    typ           TEXT    NOT NULL CHECK (typ IN ('einnahme', 'ausgabe'))
);

CREATE TABLE IF NOT EXISTS recurring (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL DEFAULT 1, -- owner (users.id)
    beschreibung     TEXT    NOT NULL,
    kategorie        TEXT    NOT NULL DEFAULT '',
    betrag_cent      INTEGER NOT NULL CHECK (betrag_cent > 0),
    typ              TEXT    NOT NULL CHECK (typ IN ('einnahme', 'ausgabe')),
    intervall_monate INTEGER NOT NULL DEFAULT 1, -- 1, 3, 6 or 12
    tag              INTEGER NOT NULL DEFAULT 1, -- booking day 1–31 (end of month in short months)
    start_datum      TEXT    NOT NULL,           -- YYYY-MM-DD, date of the first occurrence
    end_datum        TEXT                        -- YYYY-MM-DD or NULL = unlimited
);

-- Individually changed or deleted occurrences of a series (owner via the series)
CREATE TABLE IF NOT EXISTS recurring_overrides (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    recurring_id  INTEGER NOT NULL REFERENCES recurring(id),
    nummer        INTEGER NOT NULL,              -- sequence number of the occurrence, from 0
    geloescht     INTEGER NOT NULL DEFAULT 0,
    datum         TEXT,
    beschreibung  TEXT,
    kategorie     TEXT,
    betrag_cent   INTEGER,
    typ           TEXT,
    UNIQUE (recurring_id, nummer)
);

-- User accounts; password only as a hash. Demo accounts may not change their password.
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    benutzername  TEXT    NOT NULL UNIQUE,
    passwort_hash TEXT    NOT NULL,
    ist_demo      INTEGER NOT NULL DEFAULT 0
);

-- Times of failed logins (seconds since 1970), for the lock per username
CREATE TABLE IF NOT EXISTS login_fehlversuche (
    zeit          REAL    NOT NULL,
    benutzername  TEXT    NOT NULL DEFAULT ''
);
"""


def connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> sqlite3.Connection:
    """Connection for the current request (closed automatically at the end)."""
    if "db" not in g:
        g.db = connect()
    return g.db


def _close_db(_exc) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(_close_db)


def init_db(path=None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        _migrate_users(conn)
        _migrate_recurring(conn)
        _add_tag_column(conn)
        _add_column(conn, "transactions", "user_id", "INTEGER NOT NULL DEFAULT 1")
        _add_column(conn, "recurring", "user_id", "INTEGER NOT NULL DEFAULT 1")
        _add_column(conn, "login_fehlversuche", "benutzername", "TEXT NOT NULL DEFAULT ''")


def _columns(conn, table) -> set:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn, table, column, definition) -> None:
    """Adds a column to databases created before it was introduced.

    Existing rows get the default value, e.g. user_id 1 = the previously only account.
    """
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def _migrate_users(conn) -> None:
    """Converts the old table for exactly one account (CHECK id = 1) to the new format."""
    if "ist_demo" in _columns(conn, "users"):
        return
    conn.execute("ALTER TABLE users RENAME TO users_alt")
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO users (id, benutzername, passwort_hash)"
                 " SELECT id, benutzername, passwort_hash FROM users_alt")
    conn.execute("DROP TABLE users_alt")
    conn.commit()


def _add_tag_column(conn) -> None:
    """Adds the column `tag` to databases created before it was introduced."""
    if "tag" in _columns(conn, "recurring"):
        return
    conn.execute("ALTER TABLE recurring ADD COLUMN tag INTEGER NOT NULL DEFAULT 1")
    conn.execute("UPDATE recurring SET tag = CAST(substr(start_datum, 9, 2) AS INTEGER)")
    conn.commit()


def _migrate_recurring(conn) -> None:
    """Converts the old format (tag_im_monat, start_monat, end_monat) to the new one."""
    if "start_monat" not in _columns(conn, "recurring"):
        return
    old_rows = conn.execute("SELECT * FROM recurring").fetchall()
    conn.execute("DROP TABLE recurring")
    conn.executescript(SCHEMA)
    for r in old_rows:
        year, mon = (int(x) for x in r["start_monat"].split("-"))
        day = min(r["tag_im_monat"], calendar.monthrange(year, mon)[1])
        start = f"{year:04d}-{mon:02d}-{day:02d}"
        end = None
        if r["end_monat"]:
            year, mon = (int(x) for x in r["end_monat"].split("-"))
            end = f"{year:04d}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}"
        conn.execute(
            "INSERT INTO recurring (id, beschreibung, kategorie, betrag_cent, typ,"
            " intervall_monate, tag, start_datum, end_datum) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (r["id"], r["beschreibung"], r["kategorie"], r["betrag_cent"], r["typ"],
             r["tag_im_monat"], start, end),
        )
    conn.commit()


# --- Single transactions --------------------------------------------------------

# Functions taking `uid` only see and change data of this user.

def all_transactions(conn, uid):
    return conn.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY datum, id",
                        (uid,)).fetchall()


def get_transaction(conn, uid, tid):
    return conn.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?",
                        (tid, uid)).fetchone()


def add_transaction(conn, uid, iso_date, description, category, amount_cents, kind):
    conn.execute(
        "INSERT INTO transactions (user_id, datum, beschreibung, kategorie, betrag_cent, typ)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (uid, iso_date, description, category, amount_cents, kind),
    )
    conn.commit()


def update_transaction(conn, uid, tid, iso_date, description, category, amount_cents, kind):
    conn.execute(
        "UPDATE transactions SET datum = ?, beschreibung = ?, kategorie = ?,"
        " betrag_cent = ?, typ = ? WHERE id = ? AND user_id = ?",
        (iso_date, description, category, amount_cents, kind, tid, uid),
    )
    conn.commit()


def delete_transaction(conn, uid, tid):
    conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (tid, uid))
    conn.commit()


# --- Recurring transactions ------------------------------------------------------
# Functions taking `rid` but no `uid` expect a series whose ownership has already
# been checked via get_recurring(conn, uid, rid).

def all_recurring(conn, uid):
    return conn.execute(
        "SELECT * FROM recurring WHERE user_id = ? ORDER BY typ, start_datum, beschreibung", (uid,)
    ).fetchall()


def _insert_recurring(conn, uid, description, category, amount_cents, kind,
                      interval_months, day, start_date, end_date) -> int:
    cur = conn.execute(
        "INSERT INTO recurring (user_id, beschreibung, kategorie, betrag_cent, typ,"
        " intervall_monate, tag, start_datum, end_datum) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, description, category, amount_cents, kind, interval_months, day, start_date, end_date),
    )
    return cur.lastrowid


def add_recurring(conn, uid, description, category, amount_cents, kind,
                  interval_months, start_date, end_date):
    _insert_recurring(conn, uid, description, category, amount_cents, kind, interval_months,
                      int(start_date[8:10]), start_date, end_date)
    conn.commit()


def get_recurring(conn, uid, rid):
    return conn.execute("SELECT * FROM recurring WHERE id = ? AND user_id = ?", (rid, uid)).fetchone()


def _recurring(conn, rid):
    return conn.execute("SELECT * FROM recurring WHERE id = ?", (rid,)).fetchone()


def set_recurring_end(conn, rid, end_date):
    conn.execute("UPDATE recurring SET end_datum = ? WHERE id = ?", (end_date, rid))
    conn.commit()


def _delete_series(conn, rid):
    conn.execute("DELETE FROM recurring_overrides WHERE recurring_id = ?", (rid,))
    conn.execute("DELETE FROM recurring WHERE id = ?", (rid,))


def delete_recurring(conn, rid):
    _delete_series(conn, rid)
    conn.commit()


# --- Single occurrences of a series ------------------------------------------------

# Scope when changing/deleting an occurrence (keys are the form values)
SCOPES = {
    "einzeln": "nur dieser Termin",
    "vorher": "dieser und alle vorherigen Termine",
    "ab": "dieser und alle folgenden Termine",
    "alle": "alle Termine der Serie",
}


def all_overrides(conn, uid):
    return conn.execute(
        "SELECT o.* FROM recurring_overrides o JOIN recurring r ON r.id = o.recurring_id"
        " WHERE r.user_id = ?", (uid,)
    ).fetchall()


def get_override(conn, rid, number):
    return conn.execute(
        "SELECT * FROM recurring_overrides WHERE recurring_id = ? AND nummer = ?", (rid, number)
    ).fetchone()


def _upsert_override(conn, rid, number, deleted, iso_date=None, description=None,
                     category=None, amount_cents=None, kind=None):
    conn.execute(
        "INSERT INTO recurring_overrides (recurring_id, nummer, geloescht, datum, beschreibung,"
        " kategorie, betrag_cent, typ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (recurring_id, nummer) DO UPDATE SET geloescht = excluded.geloescht,"
        " datum = excluded.datum, beschreibung = excluded.beschreibung,"
        " kategorie = excluded.kategorie, betrag_cent = excluded.betrag_cent, typ = excluded.typ",
        (rid, number, int(deleted), iso_date, description, category, amount_cents, kind),
    )


def _split(conn, r, number) -> int:
    """Splits series r before occurrence `number`; returns the id of the new series (from `number`).

    The old series keeps occurrences 0 … number-1; overrides move along.
    """
    new_id = _insert_recurring(
        conn, r["user_id"], r["beschreibung"], r["kategorie"], r["betrag_cent"], r["typ"],
        r["intervall_monate"], r["tag"], fin.occurrence_date(r, number), r["end_datum"],
    )
    conn.execute(
        "UPDATE recurring_overrides SET recurring_id = ?, nummer = nummer - ?"
        " WHERE recurring_id = ? AND nummer >= ?",
        (new_id, number, r["id"], number),
    )
    conn.execute("UPDATE recurring SET end_datum = ? WHERE id = ?",
                 (fin.occurrence_date(r, number - 1), r["id"]))
    return new_id


def _is_last(r, number) -> bool:
    return not fin.is_valid_number(r, number + 1)


def _apply_to_series(conn, rid, old_date, new_date, description, category, amount_cents, kind):
    """Applies the change of one occurrence to all occurrences of series `rid`.

    If the occurrence's date was moved, all occurrences move the same way:
    new booking day, and by the same number of months. The number of occurrences stays the same.
    Individually changed occurrences take the new values, deleted ones stay deleted.
    """
    r = _recurring(conn, rid)
    count = fin.occurrence_count(r)
    offset = fin.month_index(fin.month_of(new_date)) - fin.month_index(fin.month_of(old_date))
    # Day unchanged (e.g. 30.04. with booking day 31) -> keep the booking day
    day = r["tag"] if new_date[8:10] == old_date[8:10] else int(new_date[8:10])
    start = fin.clamped_date(fin.shift_month(fin.month_of(r["start_datum"]), offset), day)
    shifted = {**dict(r), "tag": day, "start_datum": start}
    end = fin.occurrence_date(shifted, count - 1) if count else None
    conn.execute(
        "UPDATE recurring SET beschreibung = ?, kategorie = ?, betrag_cent = ?, typ = ?,"
        " tag = ?, start_datum = ?, end_datum = ? WHERE id = ?",
        (description, category, amount_cents, kind, day, start, end, rid),
    )
    conn.execute("DELETE FROM recurring_overrides WHERE recurring_id = ? AND geloescht = 0", (rid,))


def edit_occurrence(conn, rid, number, scope, iso_date, description, category, amount_cents, kind):
    """Changes occurrence `number` of series `rid` in the chosen scope (see SCOPES)."""
    r = _recurring(conn, rid)
    old_date = fin.occurrence_date(r, number)
    values = (description, category, amount_cents, kind)
    if scope == "einzeln":
        _upsert_override(conn, rid, number, False, iso_date, *values)
    elif scope == "alle":
        _apply_to_series(conn, rid, old_date, iso_date, *values)
    elif scope == "ab":
        target = _split(conn, r, number) if number > 0 else rid
        _apply_to_series(conn, target, old_date, iso_date, *values)
    elif scope == "vorher":
        if not _is_last(r, number):
            _split(conn, r, number + 1)
        _apply_to_series(conn, rid, old_date, iso_date, *values)
    else:
        raise ValueError(f"Unbekannter Umfang: {scope}")
    conn.commit()


def delete_occurrence(conn, rid, number, scope):
    """Deletes occurrence `number` of series `rid` in the chosen scope (see SCOPES)."""
    r = _recurring(conn, rid)
    if scope == "einzeln":
        _upsert_override(conn, rid, number, True)
    elif scope == "alle" or (scope == "ab" and number == 0) or (scope == "vorher" and _is_last(r, number)):
        _delete_series(conn, rid)
    elif scope == "ab":
        _delete_series(conn, _split(conn, r, number))
    elif scope == "vorher":
        _split(conn, r, number + 1)
        _delete_series(conn, rid)
    else:
        raise ValueError(f"Unbekannter Umfang: {scope}")
    conn.commit()


# --- User accounts ----------------------------------------------------------------

def get_user(conn, uid):
    return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def all_users(conn):
    return conn.execute("SELECT * FROM users ORDER BY id").fetchall()


def get_user_by_name(conn, username):
    return conn.execute("SELECT * FROM users WHERE benutzername = ?", (username,)).fetchone()


def set_user(conn, username, password_hash, is_demo=False) -> int:
    """Creates an account or sets password and demo flag of an existing one; returns the id."""
    conn.execute(
        "INSERT INTO users (benutzername, passwort_hash, ist_demo) VALUES (?, ?, ?)"
        " ON CONFLICT (benutzername) DO UPDATE SET passwort_hash = excluded.passwort_hash,"
        " ist_demo = excluded.ist_demo",
        (username, password_hash, int(is_demo)),
    )
    conn.commit()
    return get_user_by_name(conn, username)["id"]


def set_password(conn, uid, password_hash):
    conn.execute("UPDATE users SET passwort_hash = ? WHERE id = ?", (password_hash, uid))
    conn.commit()


def count_failures_since(conn, username, since: float) -> int:
    return conn.execute("SELECT count(*) FROM login_fehlversuche WHERE benutzername = ? AND zeit > ?",
                        (username, since)).fetchone()[0]


def add_failure(conn, username, timestamp: float):
    conn.execute("INSERT INTO login_fehlversuche (zeit, benutzername) VALUES (?, ?)",
                 (timestamp, username))
    conn.commit()


def clear_failures(conn, username=None):
    """Lifts the login lock for one username, or for all if none is given."""
    if username is None:
        conn.execute("DELETE FROM login_fehlversuche")
    else:
        conn.execute("DELETE FROM login_fehlversuche WHERE benutzername = ?", (username,))
    conn.commit()


def delete_user_data(conn, uid):
    """Deletes all transactions and series of a user; the account itself remains."""
    conn.execute("DELETE FROM recurring_overrides WHERE recurring_id IN"
                 " (SELECT id FROM recurring WHERE user_id = ?)", (uid,))
    conn.execute("DELETE FROM recurring WHERE user_id = ?", (uid,))
    conn.execute("DELETE FROM transactions WHERE user_id = ?", (uid,))
    conn.commit()
