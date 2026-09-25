# berichtsheft-mcp – Design

## Ziel

Berichtsheft auf online-ausbildungsnachweis.de (BLok) wöchentlich halbautomatisch
füllen. Quelle sind die Hermes-Sessions der Woche, nicht manuelle Eingabe.

## Ablauf

1. Cronjob Fr 14:00 ruft `collect_week` auf.
2. Agent fasst die Rohdaten in Stichpunkte pro Tag zusammen (Azubi-Ton).
3. Entwurf geht per Telegram an den Nutzer, der streicht/ergänzt und gibt frei.
4. Erst nach Freigabe: `fill_week`, Screenshot zurück an den Nutzer.

Ohne Freigabe wird nie etwas eingetragen.

## Komponenten

FastMCP-Server, stdio, uv. Ein Paket `berichtsheft_mcp` mit:

- `collect.py` – liest Hermes `state.db` (nur `mode=ro`), filtert Nachrichten nach
  Zeitfenstern, gruppiert pro Tag und Kategorie (`betrieb` / `schule`).
- `blok.py` – Playwright headless: Login, Woche öffnen, Felder füllen, Save prüfen.
- `server.py` – registriert die zwei Tools.

### Tool `collect_week(week: str)`

- `week` = ISO-Woche, z.B. `2026-W39`.
- Rückgabe: `{tag: {kategorie: [{session_title, user_messages[]}]}}`.
- Nur User-Nachrichten und Session-Titel, keine Tool-Outputs.
- Keine Zusammenfassung im MCP.

### Tool `fill_week(week: str, entries: dict)`

- `entries` = `{tag: {"betrieb": "...", "schule": "..."}}`.
- Füllt nur leere Felder. Bereits befüllte werden übersprungen und gemeldet.
- Rückgabe: `{filled[], skipped[], failed[], screenshot}`.

## Konfiguration

`~/.config/berichtsheft/.env` (chmod 600), im Repo nur `.env.example`:

| Variable | Beispiel |
|---|---|
| `BLOK_USERNAME` | `max.mustermann` |
| `BLOK_PASSWORD` | – |
| `HERMES_STATE_DB` | `~/.hermes/state.db` |
| `WORK_HOURS` | `mon=12:45-16:15;tue=07:30-16:15;thu=07:30-16:15;fri=07:30-16:15` |
| `SCHOOL_HOURS` | `mon=07:30-12:45;wed=07:30-12:45` |

Nichts Persönliches im Code. Repo ist public.

## Fehlerfälle

- Login fehlgeschlagen: sofort abbrechen, kein Retry (Kontosperre).
- `savestate` bleibt `empty`: einmal "Nochmal speichern!", sonst Feld in `failed[]`.
- `state.db` fehlt/gesperrt: klare Fehlermeldung, kein Absturz.

## Tests

- `tests/test_collect.py`: In-Memory-SQLite mit Fake-Nachrichten, prüft
  Zuordnung zu Tag und Kategorie inkl. Grenzzeiten.
- `fill_week`: ein Live-Test an einer echten Woche mit dem Nutzer, bevor der
  Cronjob aktiv wird.

## Repo

GitLab `lstlla/berichtsheft-mcp`, public, Push-Mirror nach GitHub (public).
`.gitignore`: `.env`, `*.png`, `.venv/`.

## Bewusst weggelassen

- Feiertage/Urlaub: leere Tage bleiben leer, Nutzer ergänzt bei Freigabe.
- Wochenkommentar.
- LLM-Zusammenfassung im MCP (macht der Agent).
