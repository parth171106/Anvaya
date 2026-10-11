"""Deterministic scenario generator (BACKEND_SCHEMA.md §5.2–§5.3). No randomness: every value is a function of an index."""
import argparse
import heapq
import itertools
from datetime import date, datetime
from typing import Iterator

from generator.formats import (IST, asa_deny, asa_in, asa_out, asa_teardown, at, eve_alert, eve_dns, fgt, fgt_success,
                               sec)

ORDER = {"fw01": 0, "ids01": 1, "vpn01": 2}
RECON_PORTS = [21, 22, 23, 25, 53, 80, 110, 139, 445, 1433, 3389, 8080]
ATTACK_USERS = ["admin", "root", "vpnuser", "administrator"]
Line = tuple[int, str, str]  # (scenario_time_ms, device, text)


def today_ist() -> date:
    return datetime.now(IST).date()


def _fw_conn(i):
    return dict(cid=77000 + i, int_=f"10.2.4.{30 + i % 10}", iport=51000 + i,
                ext=f"203.0.113.{10 + (3 * i) % 10}", eport=80 if i % 4 == 0 else 443)


def build_scripted_lines(d: date | None = None) -> list[Line]:
    d = d or today_ist()
    t0 = at(d, 10, 0)
    out: list[Line] = []
    fw = lambda ms, text: out.append((ms, "fw01", text))
    ids = lambda ms, text: out.append((ms, "ids01", text))
    vpn = lambda ms, text: out.append((ms, "vpn01", text))

    for i in range(60):
        ms = sec(t0, 10 * i)
        fw(ms, asa_out(ms, **_fw_conn(i)))
    for i in range(24):
        ms = sec(t0, 10 * i + 12)
        fw(ms, asa_teardown(ms, **_fw_conn(i), nbytes=4096 + 64 * i))
    for ext, iport, int_, times in (("203.0.113.50", 23, "10.2.4.20", ((1, 10), (4, 10), (8, 10))),
                                    ("203.0.113.51", 3389, "10.2.4.21", ((1, 40), (6, 40), (10, 40)))):
        for n, (m, s) in enumerate(times):
            ms = at(d, 10, m, s)
            fw(ms, asa_deny(ms, ext, 45000 + n, int_, iport))
    for p in range(12):
        ms = sec(at(d, 10, 2), 3 * p)
        fw(ms, asa_deny(ms, "198.51.100.9", 40101 + p, "10.2.4.18", RECON_PORTS[p]))
    ms = at(d, 10, 7, 12)
    fw(ms, asa_in(ms, 77801, "198.51.100.9", 40133, "10.2.4.18", 443))
    ms = at(d, 10, 8, 30)
    fw(ms, asa_out(ms, 77802, "203.0.113.7", 443, "10.2.4.18", 51522))

    for j in range(30):
        ms = sec(at(d, 10, 0, 12), 24 * j)
        ids(ms, eve_dns(ms, j))
    for k, (s, sport, dport) in enumerate(((5, 40100, 22), (20, 40115, 445), (35, 40130, 3389))):
        ms = at(d, 10, 2, s)
        ids(ms, eve_alert(ms, 1500000000000900 + k, "198.51.100.9", sport, "10.2.4.18", dport, "TCP", 9000001,
                          "ANVAYA-LAB SCAN Inbound TCP port sweep", "Attempted Information Leak", 2))

    for k in range(28):
        ms = sec(at(d, 10, 0, 20), 25 * k)
        vpn(ms, fgt_success(ms, k))
    for m, s in ((3, 10), (9, 50)):
        ms = at(d, 10, m, s)
        vpn(ms, fgt(ms, "fail", "203.0.113.60", "guest"))
    for f in range(40):
        ms = sec(at(d, 10, 5), f)
        vpn(ms, fgt(ms, "fail", "198.51.100.9", ATTACK_USERS[f % 4]))

    return sorted(out, key=lambda x: (x[0], ORDER[x[1]]))  # stable: ties within a device keep generation order


def steady_lines(start_ms: int) -> Iterator[Line]:
    """Benign 1x traffic from scenario 10:12:00 (start_ms) onward, merged in (time, device) order."""
    def fw01():
        for n in itertools.count():
            ms = sec(start_ms, n)
            if n % 2 == 0:
                yield ms, "fw01", asa_out(ms, 78000 + n, f"203.0.113.{10 + n % 10}", 443,
                                          f"10.2.4.{30 + (n // 2) % 10}", 52000 + n)
            else:
                p = n - 1
                yield ms, "fw01", asa_teardown(ms, 78000 + p, f"203.0.113.{10 + p % 10}", 443,
                                               f"10.2.4.{30 + (p // 2) % 10}", 52000 + p, 2048 + 32 * n)

    def ids01():
        for n in itertools.count():
            ms = sec(start_ms, 2 + 4 * n)
            yield ms, "ids01", eve_dns(ms, 30 + n)

    def vpn01():
        for n in itertools.count():
            ms = sec(start_ms, 3 + 4 * n)
            yield ms, "vpn01", fgt_success(ms, 28 + n)

    return heapq.merge(fw01(), ids01(), vpn01(), key=lambda x: (x[0], ORDER[x[1]]))


async def run(clock, sink, stop_flags: dict, d: date | None = None) -> None:
    """Send every line at its scenario time (clock converts to real time), then steady traffic until cancelled."""
    d = d or today_ist()
    for ms, device, text in itertools.chain(build_scripted_lines(d), steady_lines(at(d, 10, 12))):
        await clock.sleep_until(ms)
        if not stop_flags.get(device):
            sink.send(text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m generator.scenario")
    ap.add_argument("--dry-run", action="store_true", help="print the 207 scripted lines")
    ap.add_argument("--date", type=date.fromisoformat, default=None)
    args = ap.parse_args(argv)
    if not args.dry_run:
        ap.error("only --dry-run is supported from the CLI; start a live run with POST /api/demo/scenario/start")
    for _, _, text in build_scripted_lines(args.date):
        print(text)


if __name__ == "__main__":
    main()
