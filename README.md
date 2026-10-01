# berichtsheft-mcp

MCP server (stdio) for the [BLok](https://www.online-ausbildungsnachweis.de/blok) online Berichtsheft.

- `collect_week(week)` – reads a [Hermes](https://github.com/NousResearch/hermes-agent) `state.db` and returns
  what you worked on during a given ISO week, bucketed by day and by your work/school hours.
  Raw data only; your agent turns it into bullet points.
- `fill_week(week, entries, locations=None, dry_run=False)` – logs into BLok with headless
  Playwright and appends lines per weekday (BLok *Tagesformat*):
  `entries={"thursday": ["..."]}`, `locations={"thursday": "betrieb"}` (`schule`, `betrieb`,
  `ueberbetrieblich`). Never overwrites, skips lines that already exist, returns a screenshot path.
  Requires "Wochenformat aktivieren" to be off in BLok's Benutzereinstellungen.

Intended flow: cron job collects on Friday → agent drafts → human approves → `fill_week`.

## Setup

```bash
uv sync
mkdir -p ~/.config/berichtsheft
cp .env.example ~/.config/berichtsheft/.env && chmod 600 ~/.config/berichtsheft/.env
# edit it; either set CHROMIUM_PATH or run: uv run playwright install chromium
```

MCP client config (Hermes `config.yaml`):

```yaml
mcp_servers:
  berichtsheft:
    command: uv
    args: [--directory, /path/to/berichtsheft-mcp, run, berichtsheft-mcp]
```

## Config (`~/.config/berichtsheft/.env`)

| Var | Example |
|---|---|
| `BLOK_USERNAME` / `BLOK_PASSWORD` | your BLok login |
| `WORK_HOURS` | `mon=12:45-16:15;tue=07:30-16:15` |
| `SCHOOL_HOURS` | `mon=07:30-12:45;wed=07:30-12:45` |
| `HERMES_STATE_DB` | default `~/.hermes/state.db` |
| `CHROMIUM_PATH` | optional, e.g. `/usr/bin/chromium` |
| `SCREENSHOT_DIR` | default `~/.cache/berichtsheft` |

## Test

```bash
uv run pytest
```

MIT
