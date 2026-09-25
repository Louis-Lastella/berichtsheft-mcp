"""Read Hermes session history for one ISO week, bucketed by day and time window."""

import sqlite3
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_SHORT = {d[:3]: d for d in DAYS}


def parse_hours(spec: str) -> dict[str, tuple[time, time]]:
    """'mon=12:45-16:15;tue=07:30-16:15' -> {'monday': (12:45, 16:15), ...}"""
    out = {}
    for part in filter(None, (p.strip() for p in (spec or "").split(";"))):
        day, rng = part.split("=")
        start, end = rng.split("-")
        out[_SHORT[day.strip()[:3].lower()]] = (time.fromisoformat(start), time.fromisoformat(end))
    return out


def _category(dt: datetime, work, school) -> str | None:
    day = DAYS[dt.weekday()]
    for name, hours in (("betrieb", work), ("schule", school)):
        if day in hours and hours[day][0] <= dt.time() <= hours[day][1]:
            return name
    return None


def collect_week(db_path: str, week: str, work, school, tz: str = "Europe/Berlin") -> dict:
    """Return {day: {betrieb|schule: [{title, user[], result}]}} for ISO week like '2026-W39'.

    Only interactive sessions (not cron/subagent). A session lands in the bucket of its
    first user message inside a window; later messages of that session are appended there.
    """
    zone = ZoneInfo(tz)
    year, wk = week.upper().split("-W")
    monday = date.fromisocalendar(int(year), int(wk), 1)
    start = datetime.combine(monday, time.min, zone).timestamp()
    end = datetime.combine(monday + timedelta(days=7), time.min, zone).timestamp()

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    rows = con.execute(
        """select m.session_id, coalesce(s.title, ''), m.role, m.content, m.timestamp
           from messages m join sessions s on s.id = m.session_id
           where m.timestamp >= ? and m.timestamp < ?
             and s.source not in ('cron', 'subagent')
             and m.role in ('user', 'assistant') and m.content is not null and m.content != ''
             and (m.tool_calls is null or m.tool_calls in ('', '[]'))
           order by m.timestamp""",
        (start, end),
    ).fetchall()
    con.close()

    out = {d: {"betrieb": [], "schule": []} for d in DAYS[:5]}
    placed = {}  # session_id -> entry dict
    for sid, title, role, content, ts in rows:
        dt = datetime.fromtimestamp(ts, zone)
        if role == "user":
            cat = _category(dt, work, school)
            if sid not in placed:
                if cat is None or DAYS[dt.weekday()] not in out:
                    continue
                placed[sid] = {"title": title, "user": [], "result": ""}
                out[DAYS[dt.weekday()]][cat].append(placed[sid])
            if cat is not None:
                placed[sid]["user"].append(content.strip()[:2000])
        elif sid in placed:
            # ponytail: keeps only last assistant reply as "result", enough for a summary line
            placed[sid]["result"] = content.strip()[:1500]
    return out
