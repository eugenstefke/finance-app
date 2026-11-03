"""Finance app: manage income and expenses per month.

First time:  uv run set_password.py   (create a user account, as many as you like)
Demo:        uv run reset_demo.py     (public demo account with sample data)
Start:       uv run main.py           ->   http://127.0.0.1:5000
Online:      see PYTHONANYWHERE.md
"""

import secrets
from datetime import date
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, send_from_directory, url_for

import auth
import db
import finance as fin

app = Flask(__name__)


def _load_secret_key() -> str:
    """Key for signing the session cookies; generated once and stored."""
    path = Path(__file__).with_name(".secret_key")
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


app.secret_key = _load_secret_key()
app.jinja_env.filters["eur"] = fin.format_eur
app.jinja_env.filters["input_amount"] = fin.format_input
app.jinja_env.filters["month_name"] = fin.month_label
app.jinja_env.filters["day_name"] = fin.day_label
app.jinja_env.filters["day_total"] = fin.day_total
app.jinja_env.filters["date"] = fin.format_date
app.jinja_env.filters["rhythm"] = fin.rhythm_label
app.jinja_env.filters["occurrence_count"] = fin.occurrence_count
app.jinja_env.globals["RHYTHMS"] = fin.RHYTHMS

db.init_app(app)
auth.init_app(app)


# --- Form parsing ----------------------------------------------------------------

def _common_fields(form):
    """Validates description, category, amount and type. Raises ValueError with a message."""
    description = form.get("beschreibung", "").strip()
    if not description:
        raise ValueError("Bitte eine Beschreibung eingeben.")
    kind = form.get("typ")
    if kind not in (fin.INCOME, fin.EXPENSE):
        raise ValueError("Bitte Einnahme oder Ausgabe wählen.")
    category = form.get("kategorie", "").strip()
    amount_cents = fin.parse_amount(form.get("betrag", ""))
    return description, category, amount_cents, kind


def _parse_date(text, message):
    try:
        return date.fromisoformat(text or "").isoformat()
    except ValueError:
        raise ValueError(message) from None


def _parse_transaction(form):
    iso_date = _parse_date(form.get("datum"), "Bitte ein gültiges Datum eingeben.")
    return (iso_date, *_common_fields(form))


def _parse_recurring(form):
    description, category, amount_cents, kind = _common_fields(form)
    try:
        interval = int(form.get("intervall_monate", ""))
    except ValueError:
        interval = 0
    if interval not in fin.RHYTHMS:
        raise ValueError("Bitte einen Rhythmus wählen.")
    start = _parse_date(form.get("start_datum"), "Bitte ein gültiges Startdatum eingeben.")
    end = None
    if form.get("end_datum"):
        end = _parse_date(form.get("end_datum"), "Bitte ein gültiges Enddatum eingeben.")
        if end < start:
            raise ValueError("Das Enddatum darf nicht vor dem Startdatum liegen.")
    return description, category, amount_cents, kind, interval, start, end


def _save_recurring(conn, form):
    """Creates a recurring transaction and reports what is being entered."""
    values = _parse_recurring(form)
    db.add_recurring(conn, g.user["id"], *values)
    entry = dict(zip(
        ("beschreibung", "kategorie", "betrag_cent", "typ",
         "intervall_monate", "start_datum", "end_datum"), values))
    entry["tag"] = int(entry["start_datum"][8:10])
    text = (f"„{entry['beschreibung']}“ {fin.rhythm_label(entry['intervall_monate'])}"
            f" ab {fin.format_date(entry['start_datum'])}")
    if entry["end_datum"]:
        text += (f" bis {fin.format_date(entry['end_datum'])}:"
                 f" {fin.occurrence_count(entry)} Buchungen eingetragen.")
    else:
        text += " eingetragen (ohne Enddatum)."
    flash(text, "ok")
    return entry


# --- Routes ---------------------------------------------------------------------

# --- Progressive web app ---------------------------------------------------------------

@app.get("/sw.js")
def service_worker():
    """Served from the root so the service worker may control the whole app."""
    response = send_from_directory(app.static_folder, "sw.js", mimetype="text/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(app.static_folder, "manifest.webmanifest",
                               mimetype="application/manifest+json")


@app.route("/")
def index():
    return redirect(url_for("show_month", month=fin.current_month()))


@app.route("/monat/<month>")
def show_month(month):
    if not fin.is_valid_month(month):
        abort(404)
    conn, uid = db.get_db(), g.user["id"]
    summary = fin.month_summary(db.all_transactions(conn, uid), db.all_recurring(conn, uid), month,
                                db.all_overrides(conn, uid))

    today = date.today()
    default_date = today.isoformat() if fin.month_of(today.isoformat()) == month else f"{month}-01"

    return render_template(
        "month.html",
        summary=summary,
        prev_month=fin.shift_month(month, -1),
        next_month=fin.shift_month(month, 1),
        is_current=month == fin.current_month(),
        default_date=default_date,
        scopes=db.SCOPES,
    )


def _show_day(iso_date):
    """Month page, scrolled to the given day."""
    return redirect(url_for("show_month", month=fin.month_of(iso_date), _anchor=f"tag-{iso_date}"))


def _kind(value):
    return value if value in (fin.INCOME, fin.EXPENSE) else fin.EXPENSE


def _new_form(kind, form, status=200):
    try:
        default_date = date.fromisoformat(request.args.get("datum", "")).isoformat()
    except ValueError:
        default_date = date.today().isoformat()
    chosen = form.get("datum") or form.get("start_datum") or default_date
    back_month = fin.month_of(chosen) if fin.is_valid_month(fin.month_of(chosen)) else fin.current_month()
    return render_template("new.html", kind=kind, form=form, default_date=default_date,
                           back_month=back_month), status


@app.get("/buchung/neu")
def new_form():
    return _new_form(_kind(request.args.get("typ")), {})


@app.post("/buchung")
def new_transaction():
    try:
        if request.form.get("wiederkehrend"):
            entry = _save_recurring(db.get_db(), request.form)
            return _show_day(entry["start_datum"])
        values = _parse_transaction(request.form)
    except ValueError as e:
        # Stay on the form and keep the input
        flash(str(e), "fehler")
        return _new_form(_kind(request.form.get("typ")), request.form, 400)
    db.add_transaction(db.get_db(), g.user["id"], *values)
    flash("Buchung gespeichert.", "ok")
    return _show_day(values[0])


@app.route("/buchung/<int:tid>", methods=["GET", "POST"])
def edit_transaction(tid):
    conn = db.get_db()
    transaction = db.get_transaction(conn, g.user["id"], tid)
    if transaction is None:
        abort(404)
    if request.method == "POST":
        try:
            values = _parse_transaction(request.form)
        except ValueError as e:
            flash(str(e), "fehler")
            return redirect(url_for("edit_transaction", tid=tid))
        db.update_transaction(conn, g.user["id"], tid, *values)
        flash("Buchung aktualisiert.", "ok")
        return redirect(url_for("show_month", month=fin.month_of(values[0])))
    return render_template("edit.html", entry=transaction)


@app.post("/buchung/<int:tid>/loeschen")
def delete_transaction(tid):
    conn = db.get_db()
    transaction = db.get_transaction(conn, g.user["id"], tid)
    if transaction is None:
        abort(404)
    db.delete_transaction(conn, g.user["id"], tid)
    flash("Buchung gelöscht.", "ok")
    return redirect(url_for("show_month", month=fin.month_of(transaction["datum"])))


@app.post("/verschieben")
def move_entry():
    """Drag & drop: moves a booking to another date; for series only this one occurrence."""
    conn, uid, form = db.get_db(), g.user["id"], request.form
    try:
        new_date = _parse_date(form.get("datum"), "Ungültiges Zieldatum.")
        entry_id = int(form.get("id", ""))
        number = int(form.get("nummer") or 0)
    except ValueError:
        abort(400)

    if form.get("art") == "buchung":
        current = db.get_transaction(conn, uid, entry_id)
        if current is None:
            abort(404)
        db.update_transaction(conn, uid, entry_id, new_date, current["beschreibung"],
                              current["kategorie"], current["betrag_cent"], current["typ"])
    elif form.get("art") == "serie":
        series = db.get_recurring(conn, uid, entry_id)
        if series is None or not fin.is_valid_number(series, number):
            abort(404)
        current = db.get_override(conn, entry_id, number) or series
        if current is not series and current["geloescht"]:
            abort(404)
        db.edit_occurrence(conn, entry_id, number, "einzeln", new_date, current["beschreibung"],
                           current["kategorie"], current["betrag_cent"], current["typ"])
    else:
        abort(400)

    flash(f"„{current['beschreibung']}“ verschoben auf {fin.format_date(new_date)}.", "ok")
    return redirect(url_for("show_month", month=fin.month_of(new_date)))


UPCOMING_LIMIT = 5   # upcoming payments shown for series without end date


@app.route("/serie/<int:rid>/<int:number>", methods=["GET", "POST"])
def edit_occurrence(rid, number):
    """Change or delete one occurrence of a recurring transaction."""
    conn = db.get_db()
    series = db.get_recurring(conn, g.user["id"], rid)
    if series is None or not fin.is_valid_number(series, number):
        abort(404)
    override = db.get_override(conn, rid, number)
    if override is not None and override["geloescht"]:
        abort(404)
    current = override or {**dict(series), "datum": fin.occurrence_date(series, number)}

    if request.method == "GET":
        # Overview of the payments still due; open-ended series: only the next few
        limit = None if series["end_datum"] else UPCOMING_LIMIT
        upcoming = fin.upcoming_occurrences(series, db.all_overrides(conn, g.user["id"]),
                                            date.today().isoformat(), limit)
        return render_template(
            "edit.html", entry=current, series=series, number=number,
            count=fin.occurrence_count(series), scopes=db.SCOPES,
            upcoming=upcoming, upcoming_total=fin.day_total(upcoming), upcoming_limit=limit,
        )

    scope = request.form.get("umfang")
    if scope not in db.SCOPES:
        flash("Bitte auswählen, welche Termine geändert werden sollen.", "fehler")
        return redirect(url_for("edit_occurrence", rid=rid, number=number))

    if request.form.get("aktion") == "loeschen":
        db.delete_occurrence(conn, rid, number, scope)
        flash(f"Gelöscht: {db.SCOPES[scope]}.", "ok")
        return redirect(url_for("show_month", month=fin.month_of(current["datum"])))

    try:
        iso_date, *values = _parse_transaction(request.form)
    except ValueError as e:
        flash(str(e), "fehler")
        return redirect(url_for("edit_occurrence", rid=rid, number=number))
    db.edit_occurrence(conn, rid, number, scope, iso_date, *values)
    flash(f"Geändert: {db.SCOPES[scope]}.", "ok")
    return redirect(url_for("show_month", month=fin.month_of(iso_date)))


@app.route("/wiederkehrend", methods=["GET", "POST"])
def recurring():
    conn = db.get_db()
    if request.method == "POST":
        try:
            _save_recurring(conn, request.form)
        except ValueError as e:
            flash(str(e), "fehler")
        return redirect(url_for("recurring"))
    return render_template(
        "recurring.html",
        series_list=db.all_recurring(conn, g.user["id"]),
        today=date.today().isoformat(),
    )


@app.post("/wiederkehrend/<int:rid>/beenden")
def end_recurring(rid):
    """Sets the end date; past transactions remain unchanged."""
    conn = db.get_db()
    series = db.get_recurring(conn, g.user["id"], rid)
    if series is None:
        abort(404)
    try:
        end = _parse_date(request.form.get("end_datum"), "Bitte ein gültiges Enddatum eingeben.")
        if end < series["start_datum"]:
            raise ValueError("Das Enddatum darf nicht vor dem Startdatum liegen.")
    except ValueError as e:
        flash(str(e), "fehler")
    else:
        db.set_recurring_end(conn, rid, end)
        flash(f"Läuft jetzt bis einschließlich {fin.format_date(end)}.", "ok")
    return redirect(url_for("recurring"))


@app.post("/wiederkehrend/<int:rid>/loeschen")
def delete_recurring(rid):
    conn = db.get_db()
    if db.get_recurring(conn, g.user["id"], rid) is None:
        abort(404)
    db.delete_recurring(conn, rid)
    flash("Wiederkehrende Buchung gelöscht.", "ok")
    return redirect(url_for("recurring"))


db.init_db()

if __name__ == "__main__":
    # Locally the app runs without HTTPS, so allow cookies over http as well.
    # For access from a phone on your own Wi-Fi: set host="0.0.0.0".
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(host="127.0.0.1", port=5000, debug=True)
