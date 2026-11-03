"""Login for multiple user accounts; each one only sees its own transactions.

- Passwords are stored only as a hash (werkzeug, scrypt).
- Every page except /login requires a login.
- Every POST form needs a CSRF token (`{{ csrf_field() }}` in the template).
- After MAX_FAILED_ATTEMPTS wrong passwords, login for that username is locked
  for LOCK_SECONDS (other accounts remain usable).
- If the password changes, all other sessions become invalid.
- The demo account (public password) may not change its password.

Create an account or reset a password: `python set_password.py`
Create/reset the demo account: `python reset_demo.py`
"""

import hashlib
import secrets
import time
from datetime import timedelta

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

import db

bp = Blueprint("auth", __name__)

MIN_LENGTH = 10
MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 15 * 60
PUBLIC_ENDPOINTS = {"auth.login", "static", "service_worker", "manifest"}

# Credentials of the demo account; shown on the login page as soon as it exists.
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-zugang"

# Hash to compare against if the username does not exist (same computing time)
_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def check_new_password(password: str, repeat: str) -> None:
    """Raises ValueError if the new password is not acceptable."""
    if len(password) < MIN_LENGTH:
        raise ValueError(f"Das Passwort muss mindestens {MIN_LENGTH} Zeichen lang sein.")
    if password != repeat:
        raise ValueError("Die beiden Passwörter stimmen nicht überein.")


def _fingerprint(user) -> str:
    """Changes with every new password; stored in the session."""
    return hashlib.sha256(user["passwort_hash"].encode()).hexdigest()[:16]


def _log_in(user, remember: bool) -> None:
    session.clear()  # new session, prevents session fixation
    session["user_id"] = user["id"]
    session["auth"] = _fingerprint(user)
    session.permanent = remember


# --- CSRF ------------------------------------------------------------------------

def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_field() -> Markup:
    return Markup(f'<input type="hidden" name="csrf_token" value="{csrf_token()}">')


# --- Check before every request ------------------------------------------------------

def _before_request():
    if request.method == "POST" and current_app.config["CSRF_ENABLED"]:
        expected = session.get("csrf", "")
        if not expected or not secrets.compare_digest(expected, request.form.get("csrf_token", "")):
            abort(400, "Das Formular ist abgelaufen. Bitte die Seite neu laden und erneut versuchen.")

    if request.endpoint in PUBLIC_ENDPOINTS:
        return None

    user = db.get_user(db.get_db(), session["user_id"]) if "user_id" in session else None
    if user is None or session.get("auth") != _fingerprint(user):
        session.pop("user_id", None)
        next_path = request.full_path.rstrip("?") if request.method == "GET" else None
        return redirect(url_for("auth.login", weiter=next_path))
    g.user = user
    return None


def _safe_target(target: str | None) -> str:
    """Only allow paths of this app as redirect targets (no //other-site.com)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("index")


def init_app(app) -> None:
    app.config.setdefault("CSRF_ENABLED", True)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=True,  # HTTPS only; disabled locally in main.py
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    app.register_blueprint(bp)
    app.before_request(_before_request)
    app.jinja_env.globals["csrf_field"] = csrf_field


# --- Pages --------------------------------------------------------------------------

def _login_page(status=200):
    demo = db.get_user_by_name(db.get_db(), DEMO_USERNAME)
    credentials = (DEMO_USERNAME, DEMO_PASSWORD) if demo is not None and demo["ist_demo"] else None
    return render_template("login.html", demo=credentials), status


@bp.route("/login", methods=["GET", "POST"])
def login():
    conn = db.get_db()
    if not db.all_users(conn):
        return render_template("login.html", no_account=True)

    if request.method == "POST":
        now = time.time()
        username = request.form.get("benutzername", "").strip()
        if db.count_failures_since(conn, username, now - LOCK_SECONDS) >= MAX_FAILED_ATTEMPTS:
            flash(f"Zu viele Fehlversuche. Bitte in {LOCK_SECONDS // 60} Minuten erneut versuchen.", "fehler")
            return _login_page(429)

        user = db.get_user_by_name(conn, username)
        password = request.form.get("passwort", "")
        if user is not None and check_password_hash(user["passwort_hash"], password):
            db.clear_failures(conn, username)
            _log_in(user, bool(request.form.get("angemeldet_bleiben")))
            return redirect(_safe_target(request.args.get("weiter")))

        if user is None:
            check_password_hash(_DUMMY_HASH, password)
        db.add_failure(conn, username, now)
        flash("Benutzername oder Passwort ist falsch.", "fehler")
        return _login_page(401)

    return _login_page()


@bp.post("/logout")
def logout():
    session.clear()
    flash("Du wurdest abgemeldet.", "ok")
    return redirect(url_for("auth.login"))


@bp.route("/passwort", methods=["GET", "POST"])
def change_password():
    if g.user["ist_demo"]:
        abort(403, "Das Passwort des Demo-Zugangs kann nicht geändert werden.")
    if request.method == "POST":
        conn = db.get_db()
        try:
            if not check_password_hash(g.user["passwort_hash"], request.form.get("alt", "")):
                raise ValueError("Das bisherige Passwort ist falsch.")
            check_new_password(request.form.get("neu", ""), request.form.get("neu2", ""))
        except ValueError as e:
            flash(str(e), "fehler")
            return redirect(url_for("auth.change_password"))
        db.set_password(conn, g.user["id"], hash_password(request.form["neu"]))
        # This session stays logged in, all other devices are logged out
        _log_in(db.get_user(conn, g.user["id"]), session.permanent)
        flash("Passwort geändert. Andere Geräte wurden abgemeldet.", "ok")
        return redirect(url_for("index"))
    return render_template("password.html", min_length=MIN_LENGTH)
