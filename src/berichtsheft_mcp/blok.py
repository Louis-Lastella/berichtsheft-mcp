"""Fill the BLok weekly report (online-ausbildungsnachweis.de) via headless Playwright.

Account runs in BLok's Wochenformat (since ~10/2026 again): tableComp:monday = Betriebliche
Tätigkeiten, tuesday = Themen der Woche, wednesday = Berufsschule. Each block is a list of rows
`tableComp:<block>:inputs:N:report` (text) + `...:has` (hours "26h:45min"). N does not always
start at 0, so rows are always looked up by name prefix.

fill_week: appends rows, never overwrites (for daily drafts).
set_weeks: makes a week's blocks match exactly (overwrites text and hours, clears extra rows).
"""

import os
import re
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://www.online-ausbildungsnachweis.de/blok"
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
LOCATIONS = {"schule": "0", "betrieb": "1", "ueberbetrieblich": "2"}
BLOCKS = {"betrieb": "monday", "themen": "tuesday", "schule": "wednesday"}
HOURS_RE = re.compile(r"^\d{1,2}h:\d{2}min$")
# headless server without X: full chromium dies on GL init ("Target closed") unless GPU is off;
# CHROMIUM_PATH should point to Playwright's chrome-headless-shell (stable, fast)
LAUNCH_ARGS = ["--no-sandbox", "--disable-gpu", "--use-gl=disabled", "--disable-software-rasterizer"]


class LoginError(RuntimeError):
    pass


def launch(p):
    # CHROMIUM_PATH lets you reuse an installed chromium instead of `playwright install`
    return p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None, args=LAUNCH_ARGS)


def login(pg, user: str, password: str):
    pg.goto(f"{BASE}/login", wait_until="load")
    pg.fill("input[name^=uid]", user)
    pg.fill("input[name^=pwd]", password)
    pg.click("button[name=submitLogin]")
    try:
        # networkidle feuert vor dem Redirect -> auf echten URL-Wechsel warten
        pg.wait_for_url(lambda u: "/login" not in u, timeout=20000)
    except Exception:
        raise LoginError("Login fehlgeschlagen (kein Retry, Kontosperre vermeiden)")
    # BLok laesst seit 11/2026 oft Requests offen -> networkidle haengt 30s; load + Pause reicht
    pg.goto(f"{BASE}/report", wait_until="load")
    pg.wait_for_timeout(2000)


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
            pg.wait_for_timeout(1000)  # let the week's form settle
            return
        pg.click("a.timeforward" if shown < target else "a.timebackward")
        pg.wait_for_function(
            "m => !document.querySelector('.calendar_switch').innerText.includes(m)",
            arg=shown.strftime("%d.%m.%Y"),
        )
    raise RuntimeError(f"Woche {week} nicht erreichbar")


def _areas(pg, day):
    return pg.locator(f'textarea[name^="tableComp:{day}:inputs:"][name$=":report"]')


def _rows(pg, day) -> list[list[str]]:
    """[[textarea name, text, hours], ...] of one block, in page order."""
    return pg.evaluate(
        """d => [...document.querySelectorAll(`textarea[name^='tableComp:${d}:inputs:'][name$=':report']`)]
             .map(t => [t.name, t.value, document.querySelector(`[name='${t.name.replace(':report', ':has')}']`)?.value || ''])""",
        day,
    )


def _commit(pg, loc):
    """Fire the events BLok's autosave listens to and wait until the row is saved."""
    loc.press("End")  # keyup -> BLok marks row unsaved
    loc.evaluate("e => e.dispatchEvent(new Event('change', {bubbles: true}))")
    loc.blur()
    # Wicket may re-render the row after saving -> element detached; then check the whole page
    pg.wait_for_function(
        "e => { const t = e.isConnected && e.closest('table'); return !(t || document).querySelector('.savestate.unsaved'); }",
        arg=loc.element_handle(),
        timeout=10000,
    )


def _add_row(pg, day):
    n = _areas(pg, day).count()
    pg.click(f'a[name="tableComp:{day}:addRow"]')
    pg.wait_for_function(
        "([d, n]) => document.querySelectorAll(`textarea[name^='tableComp:${d}:inputs:'][name$=':report']`).length > n",
        arg=[day, n],
    )


def read_week(pg, week: str) -> dict:
    _goto_week(pg, week)
    return {blk: [[t, h] for _, t, h in _rows(pg, day)] for blk, day in BLOCKS.items()}


def _set_block(pg, day, rows, dry_run, log):
    cur = _rows(pg, day)
    if not cur and not rows:
        return
    if not cur:
        raise RuntimeError(f"{day}: keine Textfelder, Woche gesperrt (freigegeben/abgenommen)?")
    # extra existing rows are emptied (text "" and 0h), never deleted
    targets = list(rows) + [("", "0h:00min")] * max(0, len(cur) - len(rows))
    for i, (text, hours) in enumerate(targets):
        cur = _rows(pg, day)
        if i >= len(cur):
            if dry_run:
                log.append(f"{day}[{i}]: neue Zeile {text!r} {hours} (dry-run)")
                continue
            _add_row(pg, day)
            cur = _rows(pg, day)
        name, old_text, old_hours = cur[i]
        if old_text.strip() != text:
            log.append(f"{day}[{i}] Text: {old_text!r} -> {text!r}" + (" (dry-run)" if dry_run else ""))
            if not dry_run:
                ta = pg.locator(f'textarea[name="{name}"]')
                ta.fill(text)
                _commit(pg, ta)
        if old_hours != hours:
            log.append(f"{day}[{i}] Zeit: {old_hours} -> {hours}" + (" (dry-run)" if dry_run else ""))
            if not dry_run:
                inp = pg.locator(f'input[name="{name.replace(":report", ":has")}"]')
                inp.fill(hours)
                _commit(pg, inp)


def validate_plan(plan: dict):
    for week, blocks in plan.items():
        date.fromisocalendar(int(week[:4]), int(week.upper().split("-W")[1]), 1)
        bad = set(blocks) - set(BLOCKS)
        if bad:
            raise ValueError(f"{week}: unbekannter Block {bad}, erlaubt: {list(BLOCKS)}")
        for blk, rows in blocks.items():
            for text, hours in rows:
                if not HOURS_RE.match(hours):
                    raise ValueError(f"{week} {blk}: Zeit {hours!r} nicht im Format '26h:45min'")
                if not text.strip() and hours != "0h:00min":
                    raise ValueError(f"{week} {blk}: Stunden auf leerer Zeile")


def set_weeks(user: str, password: str, plan: dict, shot_dir: str, dry_run: bool = False,
              on_week=None) -> dict:
    """plan = {"2026-W28": {"betrieb": [[text, "26h:45min"], ...], "themen": [], "schule": [...]}}.

    Blocks not named in a week's plan stay untouched; a named block with [] gets emptied.
    Never releases (freigeben) a week. on_week(week, result) is called after each week.
    """
    validate_plan(plan)
    out = {}
    with sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": 1280, "height": 1000})
        try:
            login(pg, user, password)
            for week, blocks in plan.items():
                res = {"before": None, "changes": [], "error": None, "screenshot": None}
                try:
                    res["before"] = read_week(pg, week)
                    for blk, rows in blocks.items():
                        _set_block(pg, BLOCKS[blk], [tuple(r) for r in rows], dry_run, res["changes"])
                    if not dry_run:
                        Path(shot_dir).mkdir(parents=True, exist_ok=True)
                        res["screenshot"] = str(Path(shot_dir) / f"blok-{week}.png")
                        pg.screenshot(path=res["screenshot"], full_page=True)
                except Exception as e:
                    res["error"] = str(e).splitlines()[0][:300]
                out[week] = res
                if on_week:
                    on_week(week, res)
        finally:
            browser.close()
    return out


def fill_week(user: str, password: str, week: str, entries: dict, shot_dir: str,
              dry_run: bool = False, locations: dict | None = None) -> dict:
    """entries = {"monday": [...], ...}, locations = {"thursday": "betrieb"}; only empty rows are written."""
    res = {"week": week, "filled": [], "skipped": [], "failed": [], "screenshot": None}
    with sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": 1280, "height": 1000})
        try:
            login(pg, user, password)
            _goto_week(pg, week)

            for day, loc in (locations or {}).items():
                sel = pg.locator(f'select[name="tableComp:{day}:trspaceplus:location"]')
                if sel.input_value() == LOCATIONS[loc]:
                    continue
                if dry_run:
                    res["filled"].append(f"{day}: Ort {loc} (dry-run)")
                    continue
                sel.select_option(LOCATIONS[loc])
                pg.wait_for_timeout(1500)
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
                        _add_row(pg, day)
                        areas = _areas(pg, day)
                        empty = [areas.count() - 1]
                    ta = areas.nth(empty[0])
                    ta.fill(line)
                    try:
                        _commit(pg, ta)
                        res["filled"].append(f"{day}: {line}")
                    except Exception:
                        res["failed"].append(f"{day}: {line}")

            Path(shot_dir).mkdir(parents=True, exist_ok=True)
            res["screenshot"] = str(Path(shot_dir) / f"blok-{week}.png")
            pg.screenshot(path=res["screenshot"], full_page=True)
        finally:
            browser.close()
    return res
