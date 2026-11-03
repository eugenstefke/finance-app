# Finanz-App

**English** | [Deutsch](README.de.md)

A small, self-hosted web app for tracking income and expenses month by month.
Built with Python, Flask and SQLite. No JavaScript framework, no build step.

> The user interface is in **German** (amounts like `1.234,56 €`, German month and weekday names).
> The code, comments and tests are in English.

## Features

- **Monthly overview** – carry-over from the previous month, income, expenses and the amount still available.
  Transactions are grouped by day with a daily balance.
- **Recurring transactions** – monthly, every 3 months, half-yearly or yearly, with an optional end date.
  Booking days that don't exist in short months (e.g. the 31st) move to the end of the month.
- **Edit single occurrences of a series** – change or delete *only this one*, *this and all previous*,
  *this and all following* or *all* occurrences. Moving a date shifts all affected occurrences.
- **Drag & drop** – move a booking to another day or month by dragging it.
- **Installable as an app (PWA)** – on the phone via *Add to Home Screen*, on the desktop via the install icon
  in the address bar. Pages always come fresh from the server; only styles and icons are cached.
- **Multiple user accounts** – every account only sees its own data.
- **Optional public demo account** – with sample data, can be reset daily.
- **Security basics built in** – password hashing (scrypt), CSRF protection on every form,
  login lock after 5 failed attempts per account, all other sessions are logged out after a password change,
  secure session cookies.

## Quick start

Requirements: Python 3.10 or newer. [uv](https://docs.astral.sh/uv/) is recommended but optional.

```bash
git clone https://github.com/eugenstefke/finance-app.git
cd finance-app

# 1. Create a user account (asks for username and password)
uv run set_password.py

# 2. Start the app
uv run main.py
```

Then open <http://127.0.0.1:5000> and log in.

Without uv:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python set_password.py
python main.py
```

The database `finanzen.db` and the session key `.secret_key` are created automatically on first start.
Both are listed in `.gitignore` and must never be committed.

> Note: `pyproject.toml` declares `requires-python >= 3.14` for uv. The app itself runs on Python 3.10+.

## Managing accounts

```bash
uv run set_password.py
```

- Enter a **new** username to create another account.
- Enter an **existing** username to reset its password. This also lifts a login lock for that account
  and logs out all of its sessions.

There is intentionally no sign-up page. Accounts can only be created by whoever has access to the server.

## Demo account (optional)

```bash
uv run reset_demo.py
```

This creates the account `demo` with sample data, or resets it. Once it exists, the login page shows the credentials
(defined as `DEMO_USERNAME` / `DEMO_PASSWORD` in `auth.py`).
The demo account cannot change its password. All visitors share its data, so run the script once a day
(e.g. as a cron job or scheduled task) to clear what visitors entered.
Other accounts are never touched.

## Deployment

The app runs on any host that supports WSGI. Step-by-step instructions (in German) for
[PythonAnywhere](https://www.pythonanywhere.com/) are in [PYTHONANYWHERE.md](PYTHONANYWHERE.md).

Important when hosting it yourself:

- Serve it over **HTTPS** only. The session cookie is marked `Secure` and is not sent over plain HTTP.
  `main.py` turns this off only when started locally with `python main.py`.
- Back up `finanzen.db` regularly. It contains all data.
- Database schema changes are applied automatically on startup. Old databases are migrated in place,
  so download a backup before updating.

## Running the tests

```bash
uv run pytest
```

The tests use a temporary database and never touch `finanzen.db`.

## Project structure

| Path | Purpose |
|---|---|
| `main.py` | Flask app, routes and form parsing |
| `auth.py` | Login, logout, CSRF protection, login lock, password change |
| `db.py` | SQLite schema, migrations and all queries |
| `finance.py` | Pure calculation logic: amounts, months, recurring dates, monthly summary |
| `set_password.py` | CLI: create an account or reset a password |
| `reset_demo.py` | CLI: create/reset the demo account |
| `templates/`, `static/` | Jinja templates, CSS, icons |
| `static/manifest.webmanifest`, `static/sw.js` | PWA: app manifest and service worker (served from `/`) |
| `tests/` | pytest suite |

Amounts are stored as integers in cents. Database columns and form fields keep their original German names
(`datum`, `beschreibung`, `betrag_cent`, …), so existing databases keep working.

## License

[MIT](LICENSE)
