"""Change/delete single occurrences of a series: only this one, before, from, all."""

import pytest

import db
import finance as fin


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "series.db"
    db.init_db(path)
    c = db.connect(path)
    yield c
    c.close()


def add_rent(conn, end="2027-06-30", start="2027-01-01", amount=100000, interval=1):
    """Expense 1,000 €, monthly 01.01.–30.06.2027 (6 occurrences, numbers 0–5)."""
    db.add_recurring(conn, 1, "Miete", "", amount, fin.EXPENSE, interval, start, end)
    return conn.execute("SELECT max(id) FROM recurring").fetchone()[0]


def occurrences(conn, first="2026-12", last="2027-08"):
    """{datum: (beschreibung, betrag)} of all series occurrences in the period, via month_summary."""
    series, overrides = db.all_recurring(conn, 1), db.all_overrides(conn, 1)
    result = {}
    month = first
    while month <= last:
        for e in fin.month_summary([], series, month, overrides)["entries"]:
            result[e["datum"]] = (e["beschreibung"], e["betrag_cent"])
        month = fin.shift_month(month, 1)
    return result


def balance_after(conn, month="2027-08"):
    return fin.month_summary([], db.all_recurring(conn, 1), month, db.all_overrides(conn, 1))["carry_over"]


def change(conn, rid, number, scope, iso_date, description="Miete neu", amount=120000):
    db.edit_occurrence(conn, rid, number, scope, iso_date, description, "", amount, fin.EXPENSE)


OLD = ("Miete", 100000)
NEW = ("Miete neu", 120000)


def test_only_this_occurrence(conn):
    rid = add_rent(conn)
    change(conn, rid, 2, "einzeln", "2027-03-01")
    o = occurrences(conn)
    assert o["2027-03-01"] == NEW
    assert [o[f"2027-0{m}-01"] for m in (1, 2, 4, 5, 6)] == [OLD] * 5
    assert balance_after(conn) == -(5 * 100000 + 120000)


def test_only_this_occurrence_moved_to_another_month(conn):
    rid = add_rent(conn)
    change(conn, rid, 2, "einzeln", "2027-04-15", amount=100000)  # March occurrence moved to 15.04.
    o = occurrences(conn)
    assert "2027-03-01" not in o
    assert o["2027-04-15"] == ("Miete neu", 100000)
    assert o["2027-04-01"] == OLD
    # Carry-over at the end of March: only Jan + Feb
    assert fin.month_summary([], db.all_recurring(conn, 1), "2027-04", db.all_overrides(conn, 1))["carry_over"] == -200000


def test_this_and_all_following(conn):
    rid = add_rent(conn)
    change(conn, rid, 3, "ab", "2027-04-01")
    o = occurrences(conn)
    assert [o[f"2027-0{m}-01"] for m in range(1, 7)] == [OLD] * 3 + [NEW] * 3
    assert len(o) == 6
    assert balance_after(conn) == -(3 * 100000 + 3 * 120000)


def test_this_and_all_previous(conn):
    rid = add_rent(conn)
    change(conn, rid, 3, "vorher", "2027-04-01")
    o = occurrences(conn)
    assert [o[f"2027-0{m}-01"] for m in range(1, 7)] == [NEW] * 4 + [OLD] * 2
    assert len(o) == 6


def test_all_occurrences(conn):
    rid = add_rent(conn)
    change(conn, rid, 3, "alle", "2027-04-01")
    o = occurrences(conn)
    assert [o[f"2027-0{m}-01"] for m in range(1, 7)] == [NEW] * 6
    assert len(db.all_recurring(conn, 1)) == 1


def test_following_with_new_day_moves_all_following(conn):
    rid = add_rent(conn)
    change(conn, rid, 3, "ab", "2027-04-15")
    o = occurrences(conn)
    assert sorted(o) == ["2027-01-01", "2027-02-01", "2027-03-01",
                         "2027-04-15", "2027-05-15", "2027-06-15"]


def test_previous_with_new_day_keeps_last_occurrence(conn):
    # The end date of the front part must move along, otherwise occurrence 3 would be lost
    rid = add_rent(conn)
    change(conn, rid, 3, "vorher", "2027-04-20")
    o = occurrences(conn)
    assert sorted(o) == ["2027-01-20", "2027-02-20", "2027-03-20",
                         "2027-04-20", "2027-05-01", "2027-06-01"]


def test_following_without_end_date(conn):
    rid = add_rent(conn, end=None)
    change(conn, rid, 2, "ab", "2027-03-01")
    o = occurrences(conn, last="2028-01")
    assert o["2027-02-01"] == OLD and o["2027-03-01"] == NEW and o["2028-01-01"] == NEW


def test_quarterly_following(conn):
    rid = add_rent(conn, start="2027-01-31", end=None, interval=3)
    change(conn, rid, 1, "ab", "2027-04-30")
    o = occurrences(conn, last="2027-12")
    assert o == {"2027-01-31": OLD, "2027-04-30": NEW, "2027-07-31": NEW, "2027-10-31": NEW}


def test_day_31_kept_after_split(conn):
    rid = add_rent(conn, start="2027-01-31", end=None)
    change(conn, rid, 1, "ab", "2027-02-28")  # February occurrence (28th) without date change
    o = occurrences(conn, last="2027-04")
    assert o == {"2027-01-31": OLD, "2027-02-28": NEW, "2027-03-31": NEW, "2027-04-30": NEW}


def test_day_deliberately_changed(conn):
    rid = add_rent(conn, start="2027-01-31", end=None)
    change(conn, rid, 1, "ab", "2027-02-27")
    o = occurrences(conn, last="2027-04")
    assert o == {"2027-01-31": OLD, "2027-02-27": NEW, "2027-03-27": NEW, "2027-04-27": NEW}


def test_single_changes_overwritten_by_following_deletions_kept(conn):
    rid = add_rent(conn)
    change(conn, rid, 4, "einzeln", "2027-05-01", description="Sonder", amount=1)
    db.delete_occurrence(conn, rid, 5, "einzeln")
    change(conn, rid, 3, "ab", "2027-04-01")
    o = occurrences(conn)
    assert o["2027-05-01"] == NEW
    assert "2027-06-01" not in o


def test_single_change_before_split_kept(conn):
    rid = add_rent(conn)
    change(conn, rid, 1, "einzeln", "2027-02-01", description="Feb", amount=5)
    change(conn, rid, 3, "ab", "2027-04-01")
    assert occurrences(conn)["2027-02-01"] == ("Feb", 5)


@pytest.mark.parametrize("scope, remaining", [
    ("einzeln", ["2027-01-01", "2027-02-01", "2027-04-01", "2027-05-01", "2027-06-01"]),
    ("vorher", ["2027-04-01", "2027-05-01", "2027-06-01"]),
    ("ab", ["2027-01-01", "2027-02-01"]),
    ("alle", []),
])
def test_delete(conn, scope, remaining):
    rid = add_rent(conn)
    db.delete_occurrence(conn, rid, 2, scope)
    assert sorted(occurrences(conn)) == remaining
    assert balance_after(conn) == -len(remaining) * 100000


def test_delete_edge_cases(conn):
    rid = add_rent(conn)
    db.delete_occurrence(conn, rid, 0, "ab")          # from the first = everything
    assert occurrences(conn) == {}
    rid = add_rent(conn)
    db.delete_occurrence(conn, rid, 5, "vorher")      # up to the last = everything
    assert occurrences(conn) == {}
    assert db.all_overrides(conn, 1) == []


def test_override_ignored_after_ending(conn):
    rid = add_rent(conn)
    change(conn, rid, 5, "einzeln", "2027-06-01")
    db.set_recurring_end(conn, rid, "2027-03-31")
    assert sorted(occurrences(conn)) == ["2027-01-01", "2027-02-01", "2027-03-01"]


def test_carry_over_consistent_with_overrides(conn):
    rid = add_rent(conn, end=None)
    change(conn, rid, 2, "einzeln", "2027-05-10", amount=7)
    db.delete_occurrence(conn, rid, 4, "einzeln")
    change(conn, rid, 6, "ab", "2027-07-15", amount=3)
    series, overrides = db.all_recurring(conn, 1), db.all_overrides(conn, 1)
    month = "2026-11"
    for _ in range(14):
        next_month = fin.shift_month(month, 1)
        a = fin.month_summary([], series, month, overrides)
        b = fin.month_summary([], series, next_month, overrides)
        assert b["carry_over"] == a["available"], next_month
        month = next_month


def test_migration_day_column(tmp_path):
    path = tmp_path / "without_day.db"
    with db.connect(path) as c:
        c.executescript("""
            CREATE TABLE recurring (id INTEGER PRIMARY KEY AUTOINCREMENT, beschreibung TEXT NOT NULL,
                kategorie TEXT NOT NULL DEFAULT '', betrag_cent INTEGER NOT NULL, typ TEXT NOT NULL,
                intervall_monate INTEGER NOT NULL DEFAULT 1, start_datum TEXT NOT NULL, end_datum TEXT);
            INSERT INTO recurring (beschreibung, betrag_cent, typ, start_datum)
                VALUES ('Miete', 100, 'ausgabe', '2027-01-15');
        """)
    db.init_db(path)
    with db.connect(path) as c:
        assert db.get_recurring(c, 1, 1)["tag"] == 15
        assert db.all_overrides(c, 1) == []
