"""Run blok.set_weeks for a JSON plan; logs one JSON line per week (also to a backup file)."""
import json, os, sys, time
from pathlib import Path
from dotenv import load_dotenv
from berichtsheft_mcp import blok

load_dotenv(Path("~/.config/berichtsheft/.env").expanduser())
plan = json.load(open(sys.argv[1]))
dry = "--dry" in sys.argv
only = [a for a in sys.argv[2:] if a.startswith("20")]
if only:
    plan = {w: plan[w] for w in only}
log = Path("~/.cache/berichtsheft").expanduser() / f"set-week-log-{time.strftime('%Y%m%d-%H%M%S')}{'-dry' if dry else ''}.jsonl"


def on_week(week, res):
    line = json.dumps({week: res}, ensure_ascii=False)
    with open(log, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


blok.set_weeks(os.environ["BLOK_USERNAME"], os.environ["BLOK_PASSWORD"], plan,
               str(Path("~/.cache/berichtsheft").expanduser()), dry_run=dry, on_week=on_week)
print("LOG", log)
