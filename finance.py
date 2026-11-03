"""Pure calculation logic of the finance app: amounts, months, monthly overview.

Transactions are passed as mappings (dict or sqlite3.Row).
Amounts are always positive integers in cents; the sign follows from `typ`.
"""

import calendar
import re
from datetime import date

INCOME = "einnahme"
EXPENSE = "ausgabe"

MONTH_NAMES = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


# --- Amounts -------------------------------------------------------------------

def parse_amount(text: str) -> int:
    """Converts an input like '1.234,56' or '12.5' to cents.

    Raises ValueError on invalid input or an amount <= 0.
    """
    s = text.strip().replace("€", "").replace(" ", "")
    if not s:
        raise ValueError("Bitte einen Betrag eingeben.")
    if "," in s:
        # German format: dot = thousands separator, comma = decimal separator
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        # Treat '1.234' or '1.234.567' as thousands separators
        s = s.replace(".", "")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", s):
        raise ValueError(f"Ungültiger Betrag: {text!r}")
    euros, _, cents = s.partition(".")
    value = int(euros) * 100 + int(cents.ljust(2, "0") or 0)
    if value <= 0:
        raise ValueError("Der Betrag muss größer als 0 sein.")
    return value


def format_eur(cents: int) -> str:
    """123456 -> '1.234,56 €', -500 -> '-5,00 €'."""
    sign = "-" if cents < 0 else ""
    euros, rest = divmod(abs(cents), 100)
    euro_str = f"{euros:,}".replace(",", ".")
    return f"{sign}{euro_str},{rest:02d} €"


def format_input(cents: int) -> str:
    """Amount for a form field: 123456 -> '1234,56'."""
    euros, rest = divmod(cents, 100)
    return f"{euros},{rest:02d}"


# --- Months --------------------------------------------------------------------

def is_valid_month(month: str) -> bool:
    m = _MONTH_RE.match(month or "")
    return bool(m) and 1 <= int(m.group(2)) <= 12


def month_index(month: str) -> int:
    """Consecutive month number, e.g. for distances between months."""
    year, mon = month.split("-")
    return int(year) * 12 + int(mon) - 1


def _index_to_month(index: int) -> str:
    year, mon = divmod(index, 12)
    return f"{year:04d}-{mon + 1:02d}"


def shift_month(month: str, delta: int) -> str:
    """shift_month('2026-12', 1) -> '2027-01'."""
    return _index_to_month(month_index(month) + delta)


def current_month() -> str:
    return date.today().strftime("%Y-%m")


def month_label(month: str) -> str:
    """'2026-10' -> 'Oktober 2026'."""
    year, mon = month.split("-")
    return f"{MONTH_NAMES[int(mon) - 1]} {year}"


WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def day_label(iso_date: str) -> str:
    """'2026-10-15' -> 'Donnerstag, 15. Oktober'."""
    d = date.fromisoformat(iso_date)
    return f"{WEEKDAYS[d.weekday()]}, {d.day}. {MONTH_NAMES[d.month - 1]}"


def day_total(entries) -> int:
    """Balance of a list of transactions in cents (income positive)."""
    return sum(_signed(e) for e in entries)


def month_of(iso_date: str) -> str:
    """'2026-10-15' -> '2026-10'."""
    return iso_date[:7]


def format_date(iso_date: str) -> str:
    """'2026-10-15' -> '15.10.2026'."""
    return f"{iso_date[8:10]}.{iso_date[5:7]}.{iso_date[:4]}"


def clamped_date(month: str, day: int) -> str:
    """Date in the month; a day that is too large is cut to the month's end (31st -> 28.02.)."""
    year, mon = (int(x) for x in month.split("-"))
    day = min(day, calendar.monthrange(year, mon)[1])
    return f"{year:04d}-{mon:02d}-{day:02d}"


# --- Recurring transactions ------------------------------------------------------

RHYTHMS = {1: "monatlich", 3: "alle 3 Monate", 6: "halbjährlich", 12: "jährlich"}


def rhythm_label(interval_months: int) -> str:
    return RHYTHMS.get(interval_months, f"alle {interval_months} Monate")


def recurring_date(r, month: str) -> str:
    """Booking date of a recurring transaction in the month.

    `tag` is the desired booking day; in shorter months it is cut to the month's end.
    """
    return clamped_date(month, r["tag"])


def _start_index(r) -> int:
    return month_index(month_of(r["start_datum"]))


def occurs_in(r, month: str) -> bool:
    """Does the recurring transaction `r` fall into this month?"""
    start = _start_index(r)
    index = month_index(month)
    if index < start or (index - start) % r["intervall_monate"]:
        return False
    return not r["end_datum"] or recurring_date(r, month) <= r["end_datum"]


def recurring_for_month(recurring, month: str) -> list:
    return [r for r in recurring if occurs_in(r, month)]


def occurrence_number(r, month: str) -> int | None:
    """Sequence number (from 0) of r's occurrence in this month, otherwise None."""
    if not occurs_in(r, month):
        return None
    return (month_index(month) - _start_index(r)) // r["intervall_monate"]


def occurrence_date(r, number: int) -> str:
    """Scheduled date of occurrence `number` (from 0)."""
    month = _index_to_month(_start_index(r) + number * r["intervall_monate"])
    return recurring_date(r, month)


def is_valid_number(r, number: int) -> bool:
    return number >= 0 and (not r["end_datum"] or occurrence_date(r, number) <= r["end_datum"])


def _occurrences_before(r, month: str) -> int:
    """Number of occurrences of r in the months before `month`."""
    start = _start_index(r)
    last = month_index(month) - 1
    if r["end_datum"]:
        last = min(last, month_index(month_of(r["end_datum"])))
    if last < start:
        return 0
    count = (last - start) // r["intervall_monate"] + 1
    # The last occurrence may fall after the end date within the end month
    if not occurs_in(r, _index_to_month(start + (count - 1) * r["intervall_monate"])):
        count -= 1
    return count


def occurrence_count(r) -> int | None:
    """Total number of occurrences; None if no end date is set."""
    if not r["end_datum"]:
        return None
    return _occurrences_before(r, shift_month(month_of(r["end_datum"]), 1))


# --- Monthly overview ------------------------------------------------------------

_OVERRIDE_FIELDS = ("datum", "beschreibung", "kategorie", "betrag_cent", "typ")


def _signed(r) -> int:
    return r["betrag_cent"] if r["typ"] == INCOME else -r["betrag_cent"]


def month_summary(transactions, recurring, month: str, overrides=()) -> dict:
    """Calculates carry-over, income, expenses and available amount of a month.

    `transactions` may contain all single transactions (other months too).
    `overrides` are individually changed or deleted occurrences of series
    (key: recurring_id + nummer); a changed occurrence may also lie in
    a different month than scheduled.

    `day_balances` maps each booking day to the balance at the end of that day.

    Each entry of the result is a transaction row plus `is_recurring`; series
    occurrences additionally carry `number` and `is_changed`.
    """
    first_of_month = f"{month}-01"
    series_by_id = {r["id"]: r for r in recurring}
    # Ignore overrides for occurrences that no longer exist, e.g. after "end series"
    overrides_by_key = {
        (o["recurring_id"], o["nummer"]): o
        for o in overrides
        if o["recurring_id"] in series_by_id and is_valid_number(series_by_id[o["recurring_id"]], o["nummer"])
    }

    carry_over = sum(_signed(t) for t in transactions if t["datum"] < first_of_month)
    carry_over += sum(_signed(r) * _occurrences_before(r, month) for r in recurring)
    for (rid, number), o in overrides_by_key.items():
        r = series_by_id[rid]
        if occurrence_date(r, number) < first_of_month:
            carry_over -= _signed(r)          # remove the scheduled occurrence
        if not o["geloescht"] and o["datum"] < first_of_month:
            carry_over += _signed(o)          # add the changed occurrence

    entries = [
        {**dict(t), "is_recurring": False}
        for t in transactions
        if month_of(t["datum"]) == month
    ]
    for r in recurring_for_month(recurring, month):
        number = occurrence_number(r, month)
        if (r["id"], number) not in overrides_by_key:
            entries.append({**dict(r), "datum": recurring_date(r, month), "number": number,
                            "is_recurring": True, "is_changed": False})
    for (rid, number), o in overrides_by_key.items():
        if not o["geloescht"] and month_of(o["datum"]) == month:
            entries.append({**dict(series_by_id[rid]), **{k: o[k] for k in _OVERRIDE_FIELDS},
                            "number": number, "is_recurring": True, "is_changed": True})
    entries.sort(key=lambda e: (e["datum"], e["typ"] != INCOME, e["beschreibung"].lower()))

    income = sum(e["betrag_cent"] for e in entries if e["typ"] == INCOME)
    expenses = sum(e["betrag_cent"] for e in entries if e["typ"] == EXPENSE)

    # Running balance at the end of each booking day (carry-over included)
    day_balances = {}
    balance = carry_over
    for e in entries:
        balance += _signed(e)
        day_balances[e["datum"]] = balance

    return {
        "month": month,
        "carry_over": carry_over,
        "income": income,
        "expenses": expenses,
        "available": carry_over + income - expenses,
        "entries": entries,
        "day_balances": day_balances,
    }
