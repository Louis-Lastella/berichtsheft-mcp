"""Fill the BLok weekly report (online-ausbildungsnachweis.de) via headless Playwright.

Account runs in BLok's Tagesformat (Benutzereinstellungen, "Wochenformat aktivieren" off):
one block per weekday, tableComp:<monday..friday>, each a list of one-line activities
plus a location select (Berufsschule / Ausbildungsbetrieb / Überbetrieblich).
"""

import os
import re
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://www.online-ausbildungsnachweis.de/blok"
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
LOCATIONS = {"schule": "0", "betrieb": "1", "ueberbetrieblich": "2"}


class LoginError(RuntimeError):
    pass


def _shown_monday(pg) -> date:
    txt = pg.locator(".calendar_switch").inner_text()
    d, m, y = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", txt).groups()
    return date(int(y), int(m), int(d))


def _goto_week(pg, week: str):
    year, wk = week.upper().split("-W")
    target = date.fromisocalendar(int(year), int(wk), 1)
    for _ in range(200):
        shown = _shown_monday(pg)
        if shown == target:
            return
        pg.click("a.timeforward" if shown < target else "a.timebackward")
        pg.wait_for_function(
            "m => !document.querySelector('.calendar_switch').innerText.includes(m)",
            arg=shown.strftime("%d.%m.%Y"),
        )
    raise RuntimeError(f"Woche {week} nicht erreichbar")


def _areas(pg, day):
    return pg.locator(f'textarea[name^="tableComp:{day}:inputs:"][name$=":report"]')


def fill_week(user: str, password: str, week: str, entries: dict, shot_dir: str,
              dry_run: bool = False, locations: dict | None = None) -> dict:
    """entries = {"thursday": [...], ...}, locations = {"thursday": "betrieb"}; only empty rows are written."""
    res = {"week": week, "filled": [], "skipped": [], "failed": [], "screenshot": None}
    with sync_playwright() as p:
        # CHROMIUM_PATH lets you reuse a system chromium instead of `playwright install`
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None, args=["--no-sandbox"])
        pg = browser.new_page(viewport={"width": 1280, "height": 1000})
        try:
            pg.goto(f"{BASE}/login")
            pg.fill("input[name^=uid]", user)
            pg.fill("input[name^=pwd]", password)
            pg.click("button[name=submitLogin]")
            try:
                # networkidle feuert vor dem Redirect -> auf echten URL-Wechsel warten
                pg.wait_for_url(lambda u: "/login" not in u, timeout=20000)
            except Exception:
                raise LoginError("Login fehlgeschlagen (kein Retry, Kontosperre vermeiden)")
            pg.goto(f"{BASE}/report")
            pg.wait_for_load_state("networkidle")
            _goto_week(pg, week)

            for day, loc in (locations or {}).items():
                sel = pg.locator(f'select[name="tableComp:{day}:trspaceplus:location"]')
                if sel.input_value() == LOCATIONS[loc]:
                    continue
                if dry_run:
                    res["filled"].append(f"{day}: Ort {loc} (dry-run)")
                    continue
                sel.select_option(LOCATIONS[loc])
                pg.wait_for_load_state("networkidle")
                res["filled"].append(f"{day}: Ort {loc}")

            for day, lines in entries.items():
                existing = [v.strip() for v in _areas(pg, day).evaluate_all("a => a.map(t => t.value)")]
                todo = [ln.strip() for ln in lines if ln.strip()]
                res["skipped"] += [f"{day}: {ln}" for ln in todo if ln in existing]
                todo = [ln for ln in todo if ln not in existing]
                for line in todo:
                    if dry_run:
                        res["filled"].append(f"{day}: {line} (dry-run)")
                        continue
                    areas = _areas(pg, day)
                    empty = [i for i in range(areas.count()) if not areas.nth(i).input_value().strip()]
                    if not empty:
                        n = areas.count()
                        pg.click(f'a[name="tableComp:{day}:addRow"]')
                        pg.wait_for_function(
                            "([s, n]) => document.querySelectorAll(`textarea[name^='tableComp:${s}:inputs:'][name$=':report']`).length > n",
                            arg=[day, n],
                        )
                        areas = _areas(pg, day)
                        empty = [areas.count() - 1]
                    ta = areas.nth(empty[0])
                    ta.fill(line)
                    ta.press("End")  # fires keyup -> BLok marks row unsaved
                    ta.evaluate("t => t.dispatchEvent(new Event('change', {bubbles: true}))")
                    ta.blur()
                    try:
                        pg.wait_for_load_state("networkidle")
                        pg.wait_for_function(
                            "t => !t.closest('table').querySelector('.savestate.unsaved')",
                            arg=ta.element_handle(),
                            timeout=8000,
                        )
                        res["filled"].append(f"{day}: {line}")
                    except Exception:
                        res["failed"].append(f"{day}: {line}")

            Path(shot_dir).mkdir(parents=True, exist_ok=True)
            res["screenshot"] = str(Path(shot_dir) / f"blok-{week}.png")
            pg.screenshot(path=res["screenshot"], full_page=True)
        finally:
            browser.close()
    return res
