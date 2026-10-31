import pytest

import finance as fin


def t(iso_date, amount, kind=fin.EXPENSE, description="x", id=1):
    return {"id": id, "datum": iso_date, "beschreibung": description, "kategorie": "",
            "betrag_cent": amount, "typ": kind}


def r(amount, kind=fin.EXPENSE, start="2026-10-01", end=None, interval=1, description="r"):
    return {"id": 1, "beschreibung": description, "kategorie": "", "betrag_cent": amount,
            "typ": kind, "intervall_monate": interval, "tag": int(start[8:10]),
            "start_datum": start, "end_datum": end}


# --- Amounts ---

@pytest.mark.parametrize("text, cents", [
    ("12", 1200), ("12,5", 1250), ("12,50", 1250), ("12.50", 1250),
    ("1.234,56", 123456), ("1.234", 123400), ("1234.5", 123450),
    (" 49,90 € ", 4990), ("0,01", 1),
])
def test_parse_amount(text, cents):
    assert fin.parse_amount(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "0", "0,00", "-5", "1,234", "12,345"])
def test_parse_amount_invalid(text):
    with pytest.raises(ValueError):
        fin.parse_amount(text)


def test_format_eur():
    assert fin.format_eur(123456) == "1.234,56 €"
    assert fin.format_eur(5) == "0,05 €"
    assert fin.format_eur(-150000) == "-1.500,00 €"
    assert fin.format_input(123456) == "1234,56"


# --- Months ---

def test_shift_month_year_change():
    assert fin.shift_month("2026-12", 1) == "2027-01"
    assert fin.shift_month("2027-01", -1) == "2026-12"
    assert fin.shift_month("2026-10", -22) == "2024-12"


def test_is_valid_month():
    assert fin.is_valid_month("2026-10")
    assert not fin.is_valid_month("2026-13")
    assert not fin.is_valid_month("2026-1")
    assert not fin.is_valid_month("")


def test_month_label():
    assert fin.month_label("2026-03") == "März 2026"


def test_day_label_and_total():
    assert fin.day_label("2026-10-15") == "Donnerstag, 15. Oktober"
    assert fin.day_label("2026-11-01") == "Sonntag, 1. November"
    assert fin.day_total([t("2026-10-15", 5000, fin.INCOME), t("2026-10-15", 1250)]) == 3750


def test_recurring_day_31_in_february():
    rent = r(100, start="2026-10-31")
    assert fin.recurring_date(rent, "2027-02") == "2027-02-28"
    assert fin.recurring_date(rent, "2028-02") == "2028-02-29"
    assert fin.recurring_date(rent, "2026-12") == "2026-12-31"


# --- Rhythms ---

def _months_with_occurrence(entry, first="2026-01", count=36):
    months = [fin.shift_month(first, i) for i in range(count)]
    return [m for m in months if fin.occurs_in(entry, m)]


@pytest.mark.parametrize("interval, expected", [
    (1, ["2026-11", "2026-12", "2027-01", "2027-02", "2027-03"]),
    (3, ["2026-11", "2027-02"]),
    (6, ["2026-11"]),
    (12, ["2026-11"]),
])
def test_rhythm(interval, expected):
    entry = r(100, start="2026-11-15", end="2027-03-31", interval=interval)
    assert _months_with_occurrence(entry) == expected
    assert fin.occurrence_count(entry) == len(expected)


def test_yearly_without_end():
    insurance = r(36000, start="2026-03-01", interval=12)
    assert _months_with_occurrence(insurance) == ["2026-03", "2027-03", "2028-03"]
    assert fin.occurrence_count(insurance) is None


def test_end_date_before_booking_day_in_last_month():
    # Payment always on the 20th, end on 10.03. -> March no longer counts
    entry = r(100, start="2027-01-20", end="2027-03-10")
    assert _months_with_occurrence(entry) == ["2027-01", "2027-02"]
    assert fin.occurrence_count(entry) == 2
    assert fin.month_summary([], [entry], "2027-04")["carry_over"] == -200


def test_rhythm_label():
    assert fin.rhythm_label(1) == "monatlich"
    assert fin.rhythm_label(3) == "alle 3 Monate"
    assert fin.rhythm_label(6) == "halbjährlich"
    assert fin.rhythm_label(12) == "jährlich"


# --- Monthly overview ---

def test_simple_month():
    s = fin.month_summary(
        [t("2026-10-01", 200000, fin.INCOME), t("2026-10-05", 5000)], [], "2026-10")
    assert (s["carry_over"], s["income"], s["expenses"], s["available"]) == (0, 200000, 5000, 195000)


def test_carry_over_from_previous_months():
    transactions = [
        t("2026-09-01", 100000, fin.INCOME),
        t("2026-09-15", 30000),
        t("2026-10-03", 10000),
        t("2026-11-01", 99999),  # in the future, must not count
    ]
    s = fin.month_summary(transactions, [], "2026-10")
    assert s["carry_over"] == 70000
    assert s["available"] == 60000
    assert len(s["entries"]) == 1


def test_recurring_start_and_end():
    salary = r(300000, fin.INCOME, start="2026-10-01", end="2026-12-31")
    rent = r(100000, start="2026-10-01")

    sep = fin.month_summary([], [salary, rent], "2026-09")
    assert sep["entries"] == [] and sep["available"] == 0

    oct_ = fin.month_summary([], [salary, rent], "2026-10")
    assert oct_["carry_over"] == 0 and oct_["available"] == 200000

    nov = fin.month_summary([], [salary, rent], "2026-11")
    assert nov["carry_over"] == 200000 and nov["available"] == 400000

    # Salary ends in December, rent continues
    jan = fin.month_summary([], [salary, rent], "2027-01")
    assert jan["carry_over"] == 600000
    assert jan["income"] == 0 and jan["expenses"] == 100000
    assert jan["available"] == 500000


def test_carry_over_equals_previous_available():
    transactions = [t("2026-08-10", 4200), t("2026-11-20", 777, fin.INCOME)]
    recurring = [
        r(250000, fin.INCOME, start="2026-07-28"),
        r(9999, start="2026-09-30", end="2027-02-15"),
        r(30000, start="2026-08-15", end="2028-01-01", interval=3),
        r(5000, start="2026-06-01", interval=6),
        r(12000, start="2026-12-31", interval=12),
    ]
    month = "2026-05"
    for _ in range(36):
        next_month = fin.shift_month(month, 1)
        a = fin.month_summary(transactions, recurring, month)
        b = fin.month_summary(transactions, recurring, next_month)
        assert b["carry_over"] == a["available"]
        month = next_month


def test_entries_sorted_and_marked():
    s = fin.month_summary([t("2026-10-20", 100)], [r(500, start="2026-09-05")], "2026-10")
    assert [e["datum"] for e in s["entries"]] == ["2026-10-05", "2026-10-20"]
    assert [e["is_recurring"] for e in s["entries"]] == [True, False]
