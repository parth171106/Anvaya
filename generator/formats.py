"""Line templates (BACKEND_SCHEMA.md §5.1). Pure functions of their arguments; no randomness."""
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def at(d: date, h: int, m: int, s: int = 0) -> int:
    """Epoch ms (UTC) of h:m:s IST on date d."""
    return int(datetime(d.year, d.month, d.day, h, m, s, tzinfo=IST).timestamp() * 1000)


def ist(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, IST)


def asa_ts(ms: int) -> str:                       # %b %d %Y %H:%M:%S
    t = ist(ms)
    return f"{_MON[t.month - 1]} {t.day:02d} {t.year} {t:%H:%M:%S}"


def bsd_ts(ms: int) -> str:                       # %b %e %H:%M:%S (day padded with a space)
    t = ist(ms)
    return f"{_MON[t.month - 1]} {t.day:2d} {t:%H:%M:%S}"


def asa_out(ms, cid, ext, eport, int_, iport):
    return (f"<166>{asa_ts(ms)} fw01 : %ASA-6-302013: Built outbound TCP connection {cid} for "
            f"outside:{ext}/{eport} ({ext}/{eport}) to inside:{int_}/{iport} ({int_}/{iport})")


def asa_in(ms, cid, ext, eport, int_, iport):
    return (f"<166>{asa_ts(ms)} fw01 : %ASA-6-302013: Built inbound TCP connection {cid} for "
            f"outside:{ext}/{eport} ({ext}/{eport}) to inside:{int_}/{iport} ({int_}/{iport})")


def asa_teardown(ms, cid, ext, eport, int_, iport, nbytes):
    return (f"<166>{asa_ts(ms)} fw01 : %ASA-6-302014: Teardown TCP connection {cid} for "
            f"outside:{ext}/{eport} to inside:{int_}/{iport} duration 0:00:12 bytes {nbytes} TCP FINs")


def asa_deny(ms, ext, eport, int_, iport):
    return (f"<164>{asa_ts(ms)} fw01 : %ASA-4-106023: Deny tcp src outside:{ext}/{eport} "
            f"dst inside:{int_}/{iport} by access-group \"OUTSIDE_IN\" [0x0, 0x0]")


def eve_alert(ms, flow_id, src, sport, dst, dport, proto, sid, signature, category, severity):
    body = {
        "timestamp": f"{ist(ms):%Y-%m-%dT%H:%M:%S}.000000+0530", "flow_id": flow_id, "in_iface": "eth1",
        "event_type": "alert", "src_ip": src, "src_port": sport, "dest_ip": dst, "dest_port": dport, "proto": proto,
        "alert": {"action": "allowed", "gid": 1, "signature_id": sid, "rev": 1, "signature": signature,
                  "category": category, "severity": severity},
    }
    return f"<134>{bsd_ts(ms)} ids01 suricata[2211]: {json.dumps(body, separators=(',', ':'))}"


def eve_dns(ms, j):
    return eve_alert(ms, 1500000000000100 + j, f"10.2.4.{30 + j % 10}", 53000 + j, "203.0.113.53", 53, "UDP",
                     9000101, "ANVAYA-LAB POLICY DNS query to non-approved resolver",
                     "Potential Corporate Privacy Violation", 3)


_FGT = {
    "fail": dict(pri=185, logid="0101039426", level="alert", logdesc="SSL VPN login fail", action="ssl-login-fail",
                 reason="sslvpn_login_permission_denied", msg="SSL VPN user login failed"),
    "success": dict(pri=190, logid="0101039947", level="information", logdesc="SSL VPN tunnel up",
                    action="tunnel-up", reason="login_successfully", msg="SSL VPN tunnel established"),
}


def fgt(ms, variant, ip, user):
    v, t = _FGT[variant], ist(ms)
    return (f"<{v['pri']}>date={t:%Y-%m-%d} time={t:%H:%M:%S} devname=\"vpn01\" devid=\"FGVM01TM00000001\" "
            f"logid=\"{v['logid']}\" type=\"event\" subtype=\"vpn\" level=\"{v['level']}\" vd=\"root\" "
            f"logdesc=\"{v['logdesc']}\" action=\"{v['action']}\" tunneltype=\"ssl-web\" remip={ip} user=\"{user}\" "
            f"reason=\"{v['reason']}\" msg=\"{v['msg']}\"")


def fgt_success(ms, k):
    return fgt(ms, "success", f"203.0.113.{70 + k % 8}", ["a.sharma", "r.verma", "k.iyer", "p.nair"][k % 4])


def sec(ms: int, s: float) -> int:
    return ms + int(timedelta(seconds=s).total_seconds() * 1000)
