"""Create a user account or reset an account's password (also lifts its login lock).

Run in the project folder:
    locally:         uv run set_password.py
    PythonAnywhere:  python set_password.py   (in the Bash console, virtualenv active)
"""

import getpass
import sys

import auth
import db


def _has_terminal() -> bool:
    """True in a real terminal (PowerShell, cmd, Bash console).

    False e.g. in PyCharm's Run window: there getpass cannot read on Windows
    and would wait invisibly forever.
    """
    return sys.stdin.isatty() and sys.stdout.isatty()


def _read_password(prompt: str) -> str:
    if _has_terminal():
        return getpass.getpass(prompt)
    return input(prompt)


def main() -> int:
    if not _has_terminal():
        print("Note: No real terminal detected (e.g. PyCharm Run window).\n"
              "The password is VISIBLE while typing. For hidden input, start the script\n"
              "in a terminal (PyCharm: \"Terminal\" tab at the bottom).\n")

    db.init_db()
    conn = db.connect()
    accounts = db.all_users(conn)

    if accounts:
        print("Existing accounts: " + ", ".join(a["benutzername"] for a in accounts))
        print("Enter an existing name = reset its password, a new name = create an account.")
        entered = input(f"Username [{accounts[0]['benutzername']}]: ").strip()
        username = entered or accounts[0]["benutzername"]
    else:
        print("Create a new user account.")
        username = input("Username: ").strip()
    if not username:
        print("Aborted: no username given.")
        return 1
    existing = db.get_user_by_name(conn, username)
    print(f"Resetting the password for \"{username}\"." if existing else f"Creating new account \"{username}\".")

    print("(With hidden input no characters appear while typing – just type and press Enter.)"
          if _has_terminal() else "")
    password = _read_password(f"New password (at least {auth.MIN_LENGTH} characters): ")
    repeat = _read_password("Repeat password: ")
    try:
        auth.check_new_password(password, repeat)
    except ValueError as e:
        print(f"Aborted: {e}")
        return 1

    db.set_user(conn, username, auth.hash_password(password), is_demo=bool(existing and existing["ist_demo"]))
    db.clear_failures(conn, username)  # lift a possibly active lock
    conn.close()
    print(f"Saved. Log in with username \"{username}\". Previous sessions of this account have been logged out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
