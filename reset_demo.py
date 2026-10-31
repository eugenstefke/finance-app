"""Create the demo account or reset it to sample data.

Username and password are defined in auth.py (DEMO_USERNAME, DEMO_PASSWORD) and are
shown on the login page. All entries made by visitors are deleted.

Run in the project folder:
    locally:         uv run reset_demo.py
    PythonAnywhere:  daily as a scheduled task, see PYTHONANYWHERE.md
"""

from datetime import date

from werkzeug.security import check_password_hash

import auth
import db
import finance as fin


def _add_sample_data(conn, uid, today: date) -> None:
    year_start = f"{today.year}-01-01"
    month = fin.month_of(today.isoformat())
    prev_month = fin.shift_month(month, -1)
    for description, category, amount_cents, kind, interval, start in [
        ("Gehalt", "Arbeit", 285000, fin.INCOME, 1, f"{today.year}-01-28"),
        ("Miete", "Wohnen", 95000, fin.EXPENSE, 1, f"{today.year}-01-03"),
        ("Strom", "Wohnen", 18000, fin.EXPENSE, 3, f"{today.year}-01-15"),
        ("Handyvertrag", "Kommunikation", 2499, fin.EXPENSE, 1, year_start),
        ("Kfz-Versicherung", "Auto", 42000, fin.EXPENSE, 12, f"{today.year}-01-10"),
    ]:
        db.add_recurring(conn, uid, description, category, amount_cents, kind, interval, start, None)
    for iso_date, description, category, amount_cents, kind in [
        (f"{prev_month}-05", "Wocheneinkauf", "Lebensmittel", 8735, fin.EXPENSE),
        (f"{prev_month}-19", "Tanken", "Auto", 6420, fin.EXPENSE),
        (f"{month}-02", "Wocheneinkauf", "Lebensmittel", 9210, fin.EXPENSE),
        (f"{month}-08", "Flohmarkt", "Sonstiges", 4500, fin.INCOME),
        (f"{month}-12", "Restaurant", "Freizeit", 5680, fin.EXPENSE),
    ]:
        db.add_transaction(conn, uid, iso_date, description, category, amount_cents, kind)


def reset(conn, today: date | None = None) -> int:
    """Creates the demo account (if needed) and replaces its data; returns its id."""
    user = db.get_user_by_name(conn, auth.DEMO_USERNAME)
    if user is not None and not user["ist_demo"]:
        raise RuntimeError(f"The account \"{auth.DEMO_USERNAME}\" is not a demo account and will not be touched.")
    if user is None or not check_password_hash(user["passwort_hash"], auth.DEMO_PASSWORD):
        uid = db.set_user(conn, auth.DEMO_USERNAME, auth.hash_password(auth.DEMO_PASSWORD), is_demo=True)
    else:
        uid = user["id"]  # keep the password unchanged, otherwise all demo sessions would be logged out
    db.delete_user_data(conn, uid)
    _add_sample_data(conn, uid, today or date.today())
    db.clear_failures(conn, auth.DEMO_USERNAME)
    return uid


def main() -> int:
    db.init_db()
    conn = db.connect()
    try:
        reset(conn)
    except RuntimeError as e:
        print(f"Aborted: {e}")
        return 1
    finally:
        conn.close()
    print(f"Demo account reset. Log in with \"{auth.DEMO_USERNAME}\" / \"{auth.DEMO_PASSWORD}\".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
