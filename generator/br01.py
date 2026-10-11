"""br01 injection for SCN-04 (BACKEND_SCHEMA.md §5.4)."""
from generator.formats import ist

HOLDOUT = (2, 5, 8, 11, 14, 17)


def build_br01_lines(now_ms: int) -> list[str]:
    lines = []
    for n in range(20):
        t = ist(now_ms - (19 - n) * 3000)
        verdict = "DENY" if n in (4, 11, 17) else "ALLOW"
        dport = [443, 443, 80, 53, 443][n % 5]
        proto = "udp" if dport == 53 else "tcp"
        rule = "R-900" if verdict == "DENY" else "R-110"
        lines.append(f"EDGE|{t:%Y-%m-%d %H:%M:%S}|br01|SESSION|{verdict}|{proto}|10.2.4.{31 + n % 5}|{52300 + n}|"
                     f"203.0.113.{12 + n % 3}|{dport}|bytes={1200 + 37 * n}|rule={rule}")
    return lines
