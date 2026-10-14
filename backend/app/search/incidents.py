"""Local incident intent routing. Model-generated SQL never gains access to new tables."""
import ipaddress
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.api.errors import ApiError

INTENT = re.compile(
    r"^(?:(?:show|list|find)(?:\s+me)?\s+|(?:are there|do we have)\s+)?"
    r"(?:(?:any|all|recent|detected|possible|suspected|security)\s+)*"
    r"(?:intrusions?|incidents?|attacks?|threats?|findings?|suspicious activity)\b(?P<filters>.*)$", re.I)


def incident_answer(search, question, previous=None):
    q = question.strip().rstrip("?.!").strip()
    match = INTENT.fullmatch(q)
    following = previous and previous.get("result_type") == "incidents"
    if not match and not following:
        return None
    # An explicit new event request leaves incident mode; follow-up filters preserve its scope.
    if not match and re.match(r"^(show|list|find)\s+(?:me\s+)?(?:ssh|windows|vpn|events|logs|failed|successful)\b", q, re.I):
        return None
    started = time.perf_counter()
    now = search.clock.now_ms()
    filters = dict(previous.get("incident_filters", {})) if following else {}
    rest = match["filters"] if match else q
    today = datetime.fromtimestamp(now / 1000, ZoneInfo(search.cfg.display_tz)).replace(hour=0, minute=0, second=0, microsecond=0)
    if re.search(r"\b(?:across )?all dates\b", rest, re.I):
        filters.pop("from_ms", None)
        filters.pop("to_ms", None)
        rest = re.sub(r"\b(?:across )?all dates\b", "", rest, flags=re.I)
    elif m := re.search(r"\b(today|yesterday)\b", rest, re.I):
        start = today - timedelta(days=m[1].lower() == "yesterday")
        filters.update(from_ms=int(start.timestamp() * 1000), to_ms=int((start + timedelta(days=1)).timestamp() * 1000))
        rest = rest[:m.start()] + rest[m.end():]
    elif m := re.search(r"\b(?:in )?the last (\d{1,5}) (minutes?|hours?|days?)\b", rest, re.I):
        unit = m[2].lower()
        width = int(m[1]) * (60_000 if unit.startswith("minute") else 3_600_000 if unit.startswith("hour") else 86_400_000)
        filters.update(from_ms=now - width, to_ms=now + 1)
        rest = rest[:m.start()] + rest[m.end():]
    if m := re.search(r"(?<![\w.:])(?:\d{1,3}\.){3}\d{1,3}(?![\w.:])", rest):
        try:
            filters["ip"] = str(ipaddress.ip_address(m[0]))
        except ValueError:
            raise ApiError(422, "incident_filter", "Enter a valid IP address.") from None
        rest = rest[:m.start()] + rest[m.end():]
    if m := re.search(r"\b(open|closed)\b", rest, re.I):
        filters["status"] = m[1].lower()
        rest = rest[:m.start()] + rest[m.end():]
    if m := re.search(r"\b(low|medium|high)(?: risk| severity)?\b", rest, re.I):
        filters["level"] = m[1].title()
        rest = rest[:m.start()] + rest[m.end():]
    rest = re.sub(r"\b(only|show|me|those|ones|from|for|with|in|on|the|ip|address|and|that|are)\b", "", rest, flags=re.I)
    if rest.strip():
        raise ApiError(422, "incident_filter", "For detected incidents, try an IP address, today, yesterday, open/closed, or high/medium/low risk. Use the Incidents page for details.")
    clauses, params = [], {"now_ms": now}
    if "ip" in filters:
        clauses.append("(attacker_ip = :ip OR target_ip = :ip)")
        params["ip"] = filters["ip"]
    for field in ("status", "level"):
        if field in filters:
            clauses.append(f"{field} = :{field}")
            params[field] = filters[field]
    if "from_ms" in filters:
        clauses.append("last_time >= :from_ms AND first_time < :to_ms")
        params.update(from_ms=filters["from_ms"], to_ms=filters["to_ms"])
    sql = "SELECT incident_id FROM incidents" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY first_time DESC LIMIT 200"
    _, ids = search.repo.execute_readonly(sql, params, 2.0)
    items = [search.repo.incident_summary(row[0]) for row in ids]
    return {"question": question, "engine": "template", "model": None, "sql": sql, "params": params,
            "clock_caption": search.caption(now), "columns": [], "rows": [], "row_count": len(items),
            "took_ms": round((time.perf_counter() - started) * 1000), "result_type": "incidents",
            "incidents": items, "incident_filters": filters}
