"""FastMCP stdio server: collect_week + fill_week."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from . import blok
from .collect import collect_week as _collect, parse_hours

load_dotenv(Path(os.environ.get("BERICHTSHEFT_ENV", "~/.config/berichtsheft/.env")).expanduser())

mcp = FastMCP("berichtsheft")


def _env(key, default=None):
    val = os.environ.get(key, default)
    if val is None:
        raise RuntimeError(f"{key} fehlt in ~/.config/berichtsheft/.env")
    return val


@mcp.tool()
def collect_week(week: str) -> dict:
    """Rohdaten einer ISO-Woche (z.B. '2026-W39') aus der Hermes-Session-DB.

    Gibt pro Wochentag die Sessions im Zeitfenster 'betrieb' (WORK_HOURS) bzw.
    'schule' (SCHOOL_HOURS) zurück: Titel, User-Nachrichten, letzte Antwort.
    Ungefiltert und unzusammengefasst: der Aufrufer muss Privates aussortieren
    und daraus Stichpunkte machen.
    """
    db = Path(_env("HERMES_STATE_DB", "~/.hermes/state.db")).expanduser()
    if not db.exists():
        raise RuntimeError(f"state.db nicht gefunden: {db}")
    return _collect(str(db), week, parse_hours(_env("WORK_HOURS")), parse_hours(_env("SCHOOL_HOURS", "")))


@mcp.tool()
async def fill_week(week: str, entries: dict[str, list[str]], locations: dict[str, str] | None = None,
                    dry_run: bool = False) -> dict:
    """Trägt Stichpunkte tageweise ins BLok-Berichtsheft ein (ISO-Woche, z.B. '2026-W40').

    entries = {"thursday": [...]} mit Wochentag (monday..friday) als Schlüssel, je ein
    Stichpunkt pro Zeile. locations = {"thursday": "betrieb"} setzt den Ort des Tages
    ("schule", "betrieb", "ueberbetrieblich"). Bestehende Zeilen werden nie
    überschrieben, identische übersprungen.
    Nur nach ausdrücklicher Freigabe durch den Nutzer aufrufen. dry_run=True
    loggt nur ein und zeigt, was eingetragen würde.
    """
    locations = locations or {}
    bad = (set(entries) | set(locations)) - set(blok.DAYS)
    if bad:
        raise ValueError(f"Unbekannte Tage: {bad}, erlaubt: {list(blok.DAYS)}")
    bad = set(locations.values()) - set(blok.LOCATIONS)
    if bad:
        raise ValueError(f"Unbekannter Ort: {bad}, erlaubt: {list(blok.LOCATIONS)}")
    # sync_playwright verweigert den laufenden asyncio-Loop von FastMCP -> eigener Thread
    return await asyncio.to_thread(
        blok.fill_week,
        _env("BLOK_USERNAME"),
        _env("BLOK_PASSWORD"),
        week,
        entries,
        str(Path(_env("SCREENSHOT_DIR", "~/.cache/berichtsheft")).expanduser()),
        dry_run,
        locations,
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
