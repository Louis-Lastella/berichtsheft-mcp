import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from berichtsheft_mcp.collect import collect_week, parse_hours

TZ = ZoneInfo("Europe/Berlin")
WORK = parse_hours("mon=12:45-16:15;tue=07:30-16:15")
SCHOOL = parse_hours("mon=07:30-12:45")


def ts(s):
    return datetime.fromisoformat(s).replace(tzinfo=TZ).timestamp()


def make_db(path):
    c = sqlite3.connect(path)
    c.execute("create table sessions (id text, source text, title text)")
    c.execute("create table messages (session_id text, role text, content text, tool_calls text, timestamp real)")
    rows = [
        # KW39 2026: Mo 21.09., Di 22.09.
        ("s1", "telegram", "Server Setup", "user", "nginx reverse proxy einrichten", "2026-09-21 13:00"),
        ("s1", "telegram", "Server Setup", "assistant", "Proxy läuft", "2026-09-21 13:05"),
        ("s2", "telegram", "Moodle", "user", "hausaufgabe subnetting", "2026-09-21 09:00"),
        ("s3", "telegram", "Privat", "user", "ebay streit", "2026-09-21 18:00"),  # outside
        ("s4", "telegram", "Grenze", "user", "genau am ende", "2026-09-22 16:15"),  # inclusive end
        ("s5", "cron", "Cron", "user", "cron prompt", "2026-09-22 10:00"),  # cron ignored
        ("s6", "telegram", "Andere Woche", "user", "letzte woche", "2026-09-15 10:00"),
    ]
    c.executemany("insert or ignore into sessions values (?,?,?)", {(r[0], r[1], r[2]) for r in rows})
    c.executemany(
        "insert into messages values (?,?,?,null,?)", [(r[0], r[3], r[4], ts(r[5])) for r in rows]
    )
    c.commit()
    c.close()


def test_collect_week(tmp_path):
    db = tmp_path / "state.db"
    make_db(db)
    out = collect_week(str(db), "2026-W39", WORK, SCHOOL)

    mon = out["monday"]
    assert [s["title"] for s in mon["betrieb"]] == ["Server Setup"]
    assert mon["betrieb"][0]["user"] == ["nginx reverse proxy einrichten"]
    assert mon["betrieb"][0]["result"] == "Proxy läuft"
    assert [s["title"] for s in mon["schule"]] == ["Moodle"]
    assert [s["title"] for s in out["tuesday"]["betrieb"]] == ["Grenze"]
    flat = str(out)
    assert "ebay" not in flat and "cron prompt" not in flat and "letzte woche" not in flat
