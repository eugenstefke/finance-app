# Finanz-App

[English](README.md) | **Deutsch**

Eine kleine Web-App zum Selbst-Hosten, mit der du Einnahmen und Ausgaben Monat für Monat im Blick behältst.
Gebaut mit Python, Flask und SQLite. Kein JavaScript-Framework, kein Build-Schritt.

> Die Oberfläche ist **deutsch** (Beträge wie `1.234,56 €`, deutsche Monats- und Wochentagsnamen).
> Code, Kommentare und Tests sind englisch.

## Funktionen

- **Monatsübersicht:** Übertrag aus dem Vormonat, Einnahmen, Ausgaben und der Betrag, der noch verfügbar ist.
  Die Buchungen sind nach Tagen gruppiert, mit Tagessaldo.
- **Wiederkehrende Buchungen:** monatlich, alle 3 Monate, halbjährlich oder jährlich, optional mit Enddatum.
  Gibt es den Buchungstag in einem kurzen Monat nicht (z. B. den 31.), rutscht die Buchung aufs Monatsende.
- **Einzelne Termine einer Serie bearbeiten:** *nur diesen*, *diesen und alle vorherigen*,
  *diesen und alle folgenden* oder *alle* Termine ändern oder löschen. Ein verschobenes Datum verschiebt alle betroffenen Termine.
- **Mehrere Benutzerkonten:** Jedes Konto sieht nur seine eigenen Daten.
- **Optionales öffentliches Demo-Konto:** mit Beispieldaten, lässt sich täglich zurücksetzen.
- **Grundlegende Sicherheit eingebaut:** Passwörter als Hash (scrypt), CSRF-Schutz in jedem Formular,
  Login-Sperre nach 5 Fehlversuchen pro Konto, nach einer Passwortänderung werden alle anderen Sitzungen abgemeldet,
  sichere Sitzungs-Cookies.

## Schnellstart

Voraussetzung: Python 3.10 oder neuer. [uv](https://docs.astral.sh/uv/) wird empfohlen, ist aber nicht nötig.

```bash
git clone https://github.com/eugenstefke/finance-app.git
cd finance-app

# 1. Benutzerkonto anlegen (fragt nach Benutzername und Passwort)
uv run set_password.py

# 2. App starten
uv run main.py
```

Dann <http://127.0.0.1:5000> öffnen und anmelden.

Ohne uv:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python set_password.py
python main.py
```

Die Datenbank `finanzen.db` und der Sitzungsschlüssel `.secret_key` werden beim ersten Start automatisch angelegt.
Beide stehen in `.gitignore` und dürfen nie eingecheckt werden.

> Hinweis: `pyproject.toml` verlangt für uv `requires-python >= 3.14`. Die App selbst läuft ab Python 3.10.

## Konten verwalten

```bash
uv run set_password.py
```

- Einen **neuen** Benutzernamen eingeben, um ein weiteres Konto anzulegen.
- Einen **vorhandenen** Benutzernamen eingeben, um dessen Passwort zurückzusetzen. Das hebt auch eine Login-Sperre
  für dieses Konto auf und meldet alle seine Sitzungen ab.

Eine Registrierungsseite gibt es bewusst nicht. Konten kann nur anlegen, wer Zugriff auf den Server hat.

## Demo-Konto (optional)

```bash
uv run reset_demo.py
```

Das Skript legt das Konto `demo` mit Beispieldaten an oder setzt es zurück. Sobald es existiert, zeigt die
Anmeldeseite die Zugangsdaten an (festgelegt als `DEMO_USERNAME` / `DEMO_PASSWORD` in `auth.py`).
Das Demo-Konto kann sein Passwort nicht ändern. Alle Besucher teilen sich seine Daten. Lass das Skript deshalb
einmal täglich laufen (z. B. als Cronjob oder geplante Aufgabe), damit Eingaben von Besuchern verschwinden.
Andere Konten werden nie angetastet.

## Veröffentlichen

Die App läuft bei jedem Anbieter, der WSGI unterstützt. Eine Schritt-für-Schritt-Anleitung für
[PythonAnywhere](https://www.pythonanywhere.com/) steht in [PYTHONANYWHERE.md](PYTHONANYWHERE.md).

Wichtig beim eigenen Hosting:

- Nur über **HTTPS** ausliefern. Das Sitzungs-Cookie ist als `Secure` markiert und wird über einfaches HTTP nicht gesendet.
  `main.py` schaltet das nur ab, wenn die App lokal mit `python main.py` gestartet wird.
- `finanzen.db` regelmäßig sichern. Darin stecken alle Daten.
- Änderungen am Datenbankschema werden beim Start automatisch übernommen. Alte Datenbanken werden direkt umgestellt,
  also vor einem Update eine Sicherung herunterladen.

## Tests ausführen

```bash
uv run pytest
```

Die Tests verwenden eine temporäre Datenbank und fassen `finanzen.db` nie an.

## Projektstruktur

| Pfad | Zweck |
|---|---|
| `main.py` | Flask-App, Routen und Auswertung der Formulare |
| `auth.py` | Anmeldung, Abmeldung, CSRF-Schutz, Login-Sperre, Passwortänderung |
| `db.py` | SQLite-Schema, Migrationen und alle Abfragen |
| `finance.py` | Reine Rechenlogik: Beträge, Monate, Termine von Serien, Monatsübersicht |
| `set_password.py` | Kommandozeile: Konto anlegen oder Passwort zurücksetzen |
| `reset_demo.py` | Kommandozeile: Demo-Konto anlegen oder zurücksetzen |
| `templates/`, `static/` | Jinja-Templates und CSS |
| `tests/` | pytest-Tests |

Beträge werden als ganze Zahlen in Cent gespeichert. Datenbankspalten und Formularfelder behalten ihre ursprünglichen
deutschen Namen (`datum`, `beschreibung`, `betrag_cent`, …), damit bestehende Datenbanken weiter funktionieren.

## Lizenz

[MIT](LICENSE)
