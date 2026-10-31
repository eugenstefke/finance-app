"""Walk through the web interface with a temporary database."""

import db


# Fixture `client` (logged in, without CSRF check) comes from conftest.py


def test_full_flow(client):
    client.post("/wiederkehrend", data={
        "typ": "einnahme", "beschreibung": "Gehalt", "betrag": "2.500,00",
        "intervall_monate": "1", "start_datum": "2026-10-01", "end_datum": "",
    })
    # Via "Neue Buchung" with the "Wiederkehrend" checkbox (the date field is then disabled)
    r = client.post("/buchung", data={
        "typ": "ausgabe", "beschreibung": "Miete", "betrag": "900", "wiederkehrend": "1",
        "intervall_monate": "1", "start_datum": "2026-10-03", "end_datum": "",
    }, follow_redirects=True)
    assert "„Miete“ monatlich ab 03.10.2026 eingetragen" in r.get_data(as_text=True)
    client.post("/buchung", data={
        "typ": "ausgabe", "datum": "2026-10-15", "beschreibung": "Einkauf", "betrag": "120,50",
    })

    october = client.get("/monat/2026-10").get_data(as_text=True)
    assert "Einkauf" in october and "Gehalt" in october
    assert "1.479,50 €" in october  # 2500 - 900 - 120,50
    # One heading per day, in date order
    days = ["Donnerstag, 1. Oktober", "Samstag, 3. Oktober", "Donnerstag, 15. Oktober"]
    positions = [october.index(day) for day in days]
    assert positions == sorted(positions)
    assert october.count('class="tageskopf"') == 3

    november = client.get("/monat/2026-11").get_data(as_text=True)
    assert "1.479,50 €" in november   # carry-over
    assert "3.079,50 €" in november   # available

    september = client.get("/monat/2026-09").get_data(as_text=True)
    assert "Keine Buchungen" in september

    # Edit and delete
    assert client.get("/buchung/1").status_code == 200
    client.post("/buchung/1", data={
        "typ": "ausgabe", "datum": "2026-10-15", "beschreibung": "Einkauf", "betrag": "20,50",
    })
    assert "1.579,50 €" in client.get("/monat/2026-10").get_data(as_text=True)
    client.post("/buchung/1/loeschen")
    assert "1.600,00 €" in client.get("/monat/2026-10").get_data(as_text=True)

    # End rent at the end of December -> no more rent in January
    client.post("/wiederkehrend/2/beenden", data={"end_datum": "2026-12-31"})
    january = client.get("/monat/2027-01").get_data(as_text=True)
    assert "Miete" not in january


def test_quarterly_with_period(client):
    r = client.post("/buchung", data={
        "typ": "ausgabe", "beschreibung": "Versicherung", "betrag": "150", "wiederkehrend": "1",
        "intervall_monate": "3", "start_datum": "2026-11-15", "end_datum": "2027-11-30",
    }, follow_redirects=True)
    text = r.get_data(as_text=True)
    assert "bis 30.11.2027: 5 Buchungen eingetragen" in text
    assert "November 2026" in text  # redirect to the start month

    for month, expected in [("2026-11", True), ("2026-12", False), ("2027-02", True),
                            ("2027-11", True), ("2028-02", False)]:
        page = client.get(f"/monat/{month}").get_data(as_text=True)
        assert ("Versicherung" in page) is expected, month

    assert "5 Buchungen" in client.get("/wiederkehrend").get_data(as_text=True)


def test_edit_occurrence_via_ui(client):
    client.post("/wiederkehrend", data={
        "typ": "ausgabe", "beschreibung": "Handy", "betrag": "20", "intervall_monate": "1",
        "start_datum": "2027-01-05", "end_datum": "2027-12-31",
    })
    january = client.get("/monat/2027-01").get_data(as_text=True)
    assert "/serie/1/0" in january

    page = client.get("/serie/1/3").get_data(as_text=True)   # April occurrence
    assert "Termin 4 von 12" in page
    assert 'value="2027-04-05"' in page
    for text in ("Nur dieser Termin", "Dieser und alle vorherigen Termine",
                 "Dieser und alle folgenden Termine", "Alle Termine der Serie"):
        assert text in page

    form = {"typ": "ausgabe", "datum": "2027-04-05", "beschreibung": "Handy neu",
            "kategorie": "", "betrag": "25", "aktion": "speichern"}
    # Without choosing a scope nothing is changed
    r = client.post("/serie/1/3", data=form, follow_redirects=True)
    assert "Bitte auswählen" in r.get_data(as_text=True)

    r = client.post("/serie/1/3", data={**form, "umfang": "ab"}, follow_redirects=True)
    assert "Geändert: dieser und alle folgenden Termine." in r.get_data(as_text=True)
    assert "Handy neu" in client.get("/monat/2027-12").get_data(as_text=True)
    assert "Handy neu" not in client.get("/monat/2027-03").get_data(as_text=True)

    # Delete a single occurrence
    r = client.post("/serie/1/1", data={**form, "aktion": "loeschen", "umfang": "einzeln"},
                    follow_redirects=True)
    assert "Gelöscht: nur dieser Termin." in r.get_data(as_text=True)
    assert "Handy" not in client.get("/monat/2027-02").get_data(as_text=True)
    assert client.get("/serie/1/1").status_code == 404
    assert client.get("/serie/1/99").status_code == 404


def test_recurring_invalid(client):
    base = {"typ": "ausgabe", "beschreibung": "X", "betrag": "10", "wiederkehrend": "1",
            "intervall_monate": "1", "start_datum": "2026-11-15"}
    r = client.post("/buchung", data={**base, "end_datum": "2026-10-01"}, follow_redirects=True)
    assert "Enddatum darf nicht vor dem Startdatum" in r.get_data(as_text=True)
    r = client.post("/buchung", data={**base, "intervall_monate": "2"}, follow_redirects=True)
    assert "Rhythmus" in r.get_data(as_text=True)


def test_migration_old_format(tmp_path):
    path = tmp_path / "old.db"
    with db.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE recurring (id INTEGER PRIMARY KEY, beschreibung TEXT, kategorie TEXT,
                betrag_cent INTEGER, typ TEXT, tag_im_monat INTEGER, start_monat TEXT, end_monat TEXT);
            INSERT INTO recurring VALUES (1, 'Miete', '', 90000, 'ausgabe', 31, '2026-02', '2026-06');
            INSERT INTO recurring VALUES (2, 'Gehalt', '', 250000, 'einnahme', 1, '2026-10', NULL);
        """)
    db.init_db(path)
    with db.connect(path) as conn:
        rows = [dict(row) for row in db.all_recurring(conn, 1)]
    assert {row["beschreibung"]: (row["start_datum"], row["end_datum"], row["intervall_monate"]) for row in rows} == {
        "Miete": ("2026-02-28", "2026-06-30", 1),
        "Gehalt": ("2026-10-01", None, 1),
    }


def test_invalid_input(client):
    r = client.post("/buchung", data={"typ": "ausgabe", "datum": "2026-10-15",
                                      "beschreibung": "X", "betrag": "abc"},
                    follow_redirects=True)
    assert "Ungültiger Betrag" in r.get_data(as_text=True)
    assert client.get("/monat/2026-13").status_code == 404
    assert client.get("/buchung/999").status_code == 404
