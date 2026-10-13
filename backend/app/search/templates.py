"""Template fallback T1–T5 (TRD.md §12.4). Captured values are restricted by the regexes, so they are safe literals."""
import re
from dataclasses import dataclass

LIST_COLS = "time, device, class_name, src_ip, src_port, dst_ip, dst_port, action"
SUGGESTIONS = ["What did 10.2.4.18 do in the last hour?", "Which IPs had failed VPN logins in the last 15 minutes?",
               "Show denied connections to 10.2.4.18", "Show events from br01"]
_IP = r"(?P<ip>\d{1,3}(\.\d{1,3}){3})"
T1 = re.compile(rf"^what did {_IP} do in the last (?P<n>\d+|an|one)? ?(?P<unit>minutes?|hours?)$", re.I)
T2 = re.compile(r"^(which|what) ips? had failed (?P<service>vpn )?logins?( in the last (?P<n>\d+) (?P<unit>minutes?|hours?))?$", re.I)
T3 = re.compile(rf"^(show )?denied connections to {_IP}$", re.I)
T4 = re.compile(r"^(show )?events from (?P<device>[a-z0-9_.:-]+)$", re.I)
T5 = re.compile(r"^how many events did each device send$", re.I)


@dataclass
class TemplateHit:
    id: str
    sql: str


def _window_ms(n: str | None, unit: str) -> int:
    k = 1 if n in (None, "", "an", "one") else int(n)
    return k * (60_000 if unit.lower().startswith("minute") else 3_600_000)


def match_template(question: str) -> TemplateHit | None:
    q = question.strip()
    q = q[:-1].rstrip() if q.endswith("?") else q
    if m := T1.match(q):
        ip = m["ip"]
        return TemplateHit("T1", f"SELECT {LIST_COLS} FROM events WHERE (src_ip = '{ip}' OR dst_ip = '{ip}') AND time >= "
                                 f":now_ms - {_window_ms(m['n'], m['unit'])} ORDER BY time DESC LIMIT 200")
    if m := T2.match(q):
        w = _window_ms(m["n"], m["unit"]) if m["n"] else 900_000
        service = " AND format = 'fortigate-kv'" if m["service"] else ""
        return TemplateHit("T2", "SELECT src_ip, COUNT(*) AS failed_logins FROM events WHERE class_uid = 3002 AND "
                                 f"status = 'Failure'{service} AND time >= :now_ms - {w} GROUP BY src_ip ORDER BY failed_logins "
                                 "DESC LIMIT 200")
    if m := T3.match(q):
        return TemplateHit("T3", "SELECT time, device, src_ip, src_port, dst_port, action FROM events WHERE class_uid = "
                                 f"4001 AND action = 'Denied' AND dst_ip = '{m['ip']}' ORDER BY time DESC LIMIT 200")
    if m := T4.match(q):
        return TemplateHit("T4", f"SELECT {LIST_COLS} FROM events WHERE device = '{m['device']}' COLLATE NOCASE ORDER BY time "
                                 "DESC LIMIT 200")
    if T5.match(q):
        return TemplateHit("T5", "SELECT device, COUNT(*) AS events FROM events GROUP BY device ORDER BY events DESC "
                                 "LIMIT 200")
    # Practical searches do not silently impose a recent time window on imported logs.
    window = re.search(r" in the last (\d{1,5}|an?|one) (minutes?|hours?|days?)$", q, re.I)
    time_filter = ""
    if window:
        n = 1 if window[1].lower() in ('a', 'an', 'one') else int(window[1])
        unit = window[2].lower()
        ms = n * (86_400_000 if unit.startswith('day') else 3_600_000 if unit.startswith('hour') else 60_000)
        time_filter = f" AND time >= :now_ms - {ms}"
        q = q[:window.start()]
    basic = re.sub(r"^(show|list|find)\s+", "", q, flags=re.I).lower()
    cols = LIST_COLS + ", user_name, status"
    condition = None
    if basic in ('events', 'logs', 'all events', 'all logs', 'recent events', 'recent logs', 'latest events', 'latest logs'):
        condition = '1 = 1'
    elif m := re.fullmatch(r"(?:(failed|successful) )?(ssh|vpn|windows)(?: (?:logs|events|logins))?", basic):
        fmt = {'ssh': 'openssh-journal', 'vpn': 'fortigate-kv', 'windows': 'windows-security-json'}[m[2]]
        condition = f"class_uid = 3002 AND format = '{fmt}'"
        if m[1]:
            condition += " AND status = '" + ('Failure' if m[1] == 'failed' else 'Success') + "'"
    elif basic in ('failed logins', 'successful logins'):
        condition = "class_uid = 3002 AND status = '" + ('Failure' if basic.startswith('failed') else 'Success') + "'"
    elif basic in ('denied connections', 'blocked connections'):
        condition = "class_uid = 4001 AND action = 'Denied'"
    elif m := re.fullmatch(r"(?:events|logs) from ([a-z0-9_.:-]+)", basic):
        condition = f"device = '{m[1]}' COLLATE NOCASE"
    elif m := re.fullmatch(r"(?:events for|logs for) (\d{1,3}(?:\.\d{1,3}){3})", basic):
        condition = f"(src_ip = '{m[1]}' OR dst_ip = '{m[1]}')"
    elif re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", basic):
        condition = f"(src_ip = '{basic}' OR dst_ip = '{basic}')"
    if condition is not None:
        return TemplateHit('practical', f"SELECT {cols} FROM events WHERE {condition}{time_filter} ORDER BY time DESC LIMIT 200")
    return None


def workspace_suggestions(repo, demo_mode=False):
    if demo_mode:
        return SUGGESTIONS
    items = ['Show recent events', 'How many events did each device send?']
    sources = sorted(repo.sources(), key=lambda s: s['last_seen'], reverse=True)
    if any(s['format'] == 'openssh-journal' for s in sources):
        items.append('Show SSH logs')
    for source in sources:
        device = source['device']
        if re.fullmatch(r'[a-zA-Z0-9_.:-]+', device):
            items.append(f'Show events from {device}')
        if len(items) == 4:
            break
    for fallback in ('Show failed logins', 'Show denied connections'):
        if len(items) < 4:
            items.append(fallback)
    return items
