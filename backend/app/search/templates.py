"""Template fallback T1–T5 (TRD.md §12.4). Captured values are restricted by the regexes, so they are safe literals."""
import re
from dataclasses import dataclass

LIST_COLS = "time, device, class_name, src_ip, src_port, dst_ip, dst_port, action"
SUGGESTIONS = ["What did 10.2.4.18 do in the last hour?", "Which IPs had failed VPN logins in the last 15 minutes?",
               "Show denied connections to 10.2.4.18", "Show events from br01"]
_IP = r"(?P<ip>\d{1,3}(\.\d{1,3}){3})"
T1 = re.compile(rf"^what did {_IP} do in the last (?P<n>\d+|an|one)? ?(?P<unit>minutes?|hours?)$", re.I)
T2 = re.compile(r"^(which|what) ips? had failed (vpn )?logins?( in the last (?P<n>\d+) (?P<unit>minutes?|hours?))?$", re.I)
T3 = re.compile(rf"^(show )?denied connections to {_IP}$", re.I)
T4 = re.compile(r"^(show )?events from (?P<device>[a-z0-9-]+)$", re.I)
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
        return TemplateHit("T2", "SELECT src_ip, COUNT(*) AS failed_logins FROM events WHERE class_uid = 3002 AND "
                                 f"status = 'Failure' AND time >= :now_ms - {w} GROUP BY src_ip ORDER BY failed_logins "
                                 "DESC LIMIT 200")
    if m := T3.match(q):
        return TemplateHit("T3", "SELECT time, device, src_ip, src_port, dst_port, action FROM events WHERE class_uid = "
                                 f"4001 AND action = 'Denied' AND dst_ip = '{m['ip']}' ORDER BY time DESC LIMIT 200")
    if m := T4.match(q):
        return TemplateHit("T4", f"SELECT {LIST_COLS} FROM events WHERE device = '{m['device'].lower()}' ORDER BY time "
                                 "DESC LIMIT 200")
    if T5.match(q):
        return TemplateHit("T5", "SELECT device, COUNT(*) AS events FROM events GROUP BY device ORDER BY events DESC "
                                 "LIMIT 200")
    return None
