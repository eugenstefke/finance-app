# Finanz-App auf PythonAnywhere veröffentlichen

Ersetze überall `BENUTZER` durch deinen PythonAnywhere-Benutzernamen.

## 1. Dateien hochladen

**Diese Dateien gehören hoch:** `main.py`, `auth.py`, `db.py`, `finance.py`, `set_password.py`,
`reset_demo.py`, `requirements.txt`, die Ordner `templates/` und `static/`.

**Diese NICHT** (stehen auch in `.gitignore`): `finanzen.db` (deine Daten), `.secret_key`, `.venv/`, `.idea/`.

Zwei Wege:
- **Mit Git (empfohlen):** Projekt in ein **privates** GitHub-Repository legen, dann in einer
  PythonAnywhere-Bash-Konsole: `git clone https://github.com/…/finanz-app.git ~/finanz-app`.
  Updates später mit `cd ~/finanz-app && git pull`.
- **Ohne Git:** Im Reiter *Files* den Ordner `/home/BENUTZER/finanz-app` anlegen und die Dateien hochladen.

Möchtest du deine lokalen Buchungen mitnehmen, lade `finanzen.db` einmalig zusätzlich in den Ordner hoch.

## 2. Virtualenv und Pakete (Bash-Konsole)

Im Reiter *Consoles* eine **Bash**-Konsole öffnen:

```bash
cd ~/finanz-app
mkvirtualenv --python=python3.13 finanz-venv     # neueste dort verfügbare Version nehmen
pip install -r requirements.txt
```

(Die Angabe `requires-python >= 3.14` in `pyproject.toml` gilt nur für uv; die App läuft ab Python 3.10.)

## 3. Benutzerkonto anlegen

```bash
cd ~/finanz-app
workon finanz-venv
python set_password.py
```

Benutzername und ein **langes** Passwort wählen (mind. 10 Zeichen, besser ein Passwort-Manager).
Dasselbe Skript setzt später ein vergessenes Passwort zurück und hebt eine Login-Sperre auf.
Mit einem neuen Benutzernamen legt es ein weiteres Konto an. Jedes Konto sieht nur seine eigenen Buchungen.

### Optional: öffentliches Demo-Konto

```bash
python reset_demo.py
```

Das Skript legt das Konto `demo` mit Beispieldaten an. Die Zugangsdaten stehen in `auth.py`
(`DEMO_USERNAME`, `DEMO_PASSWORD`) und erscheinen dann auf der Anmeldeseite. Das Demo-Konto kann sein
Passwort nicht ändern. Alle Besucher teilen sich die Demo-Daten.

Damit Eingaben von Besuchern nicht liegen bleiben, das Skript täglich laufen lassen:
Reiter *Tasks* → **Scheduled tasks**, Uhrzeit wählen, Befehl:

```
/home/BENUTZER/.virtualenvs/finanz-venv/bin/python /home/BENUTZER/finanz-app/reset_demo.py
```

Ohne Demo: Skript einfach nicht ausführen. Ein vorhandenes Demo-Konto entfernst du in der Bash-Konsole mit
`sqlite3 ~/finanz-app/finanzen.db "DELETE FROM users WHERE benutzername = 'demo'"`.

## 4. Web-App einrichten (Reiter *Web*)

1. **Add a new web app** → **Manual configuration** (nicht „Flask“) → gleiche Python-Version wie oben.
2. **Virtualenv:** `/home/BENUTZER/.virtualenvs/finanz-venv`
3. **Source code:** `/home/BENUTZER/finanz-app`
4. **WSGI configuration file** (Link anklicken), gesamten Inhalt ersetzen durch:

   ```python
   import sys

   pfad = "/home/BENUTZER/finanz-app"
   if pfad not in sys.path:
       sys.path.insert(0, pfad)

   from main import app as application
   ```

5. **Static files:** URL `/static/` → Verzeichnis `/home/BENUTZER/finanz-app/static`
6. **Security:** **Force HTTPS** einschalten. (Wichtig: Das Anmelde-Cookie wird nur über HTTPS gesendet.)
7. Oben auf **Reload** klicken und `https://BENUTZER.pythonanywhere.com` öffnen.

## 5. Nach Änderungen am Code

Neue Dateien hochladen bzw. `git pull`, bei geänderten Paketen `pip install -r requirements.txt`,
dann im Reiter *Web* auf **Reload**. Die Datenbank wird beim Start automatisch auf den neuen Stand gebracht.
Beim Umstieg auf mehrere Konten gehören alle bisherigen Buchungen deinem bisherigen Konto.
**Vorher `finanzen.db` herunterladen**, als Sicherung.

## Datensicherung

Alle Daten stecken in `/home/BENUTZER/finanz-app/finanzen.db`. Regelmäßig im Reiter *Files* herunterladen.

## Wenn etwas nicht geht

- Fehlermeldungen stehen im Reiter *Web* unter **Log files → Error log**.
- „Formular ist abgelaufen“: Seite neu laden (passiert z.B. nach dem Abmelden in einem anderen Tab).
- Anmeldung klappt nicht trotz richtigem Passwort: **Force HTTPS** prüfen und die Seite über `https://` aufrufen.
- Hinweis bei kostenlosen Konten: Die Web-App muss alle 3 Monate im Reiter *Web* verlängert werden
  („Run until 3 months from today“).
