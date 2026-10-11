"""`make bench`: measured ingest throughput (IMPLEMENTATION_PLAN.md §4.6). Writes a row only from a successful run."""
import argparse
import itertools
import json
import os
import platform
import socket
import statistics
import sys
import threading
import time
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generator.formats import at  # noqa: E402
from generator.scenario import steady_lines  # noqa: E402

N_LINES, DURATION_S, WARMUP_S = 50_000, 30, 5
HEADER = ("| Date | Raw events/s (sustained) | Normalized events/s | UDP loss | p95 pipeline catch-up (s) | Machine |\n"
          "|---|---|---|---|---|---|\n")


def get(api, path):
    with urllib.request.urlopen(f"{api}{path}", timeout=5) as r:
        return json.load(r)


def post(api, path, body=b"{}"):
    req = urllib.request.Request(f"{api}{path}", data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def machine() -> str:
    cpu = platform.processor() or platform.machine()
    try:
        cpu = next(ln.split(":", 1)[1].strip() for ln in open("/proc/cpuinfo") if ln.startswith("model name"))
    except (OSError, StopIteration):
        pass
    ram = "?"
    try:
        kb = int(next(ln.split()[1] for ln in open("/proc/meminfo") if ln.startswith("MemTotal")))
        ram = f"{kb / 1024 / 1024:.0f} GB"
    except (OSError, StopIteration):
        try:
            ram = f"{os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 1024 ** 3:.0f} GB"
        except (ValueError, OSError, AttributeError):
            if sys.platform == "win32":
                import ctypes

                class Mem(ctypes.Structure):
                    _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                                ("avail", ctypes.c_ulonglong), ("pf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong),
                                ("v", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ext", ctypes.c_ulonglong)]
                m = Mem(len=ctypes.sizeof(Mem))
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                    ram = f"{m.total / 1024 ** 3:.0f} GB"
    return f"{cpu} · {os.cpu_count()} cores · {ram} RAM · {platform.system()} {platform.release()}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--out", default="docs/BENCHMARKS.md")
    ap.add_argument("--udp", default="127.0.0.1:5514")
    a = ap.parse_args()
    api = a.api.rstrip("/") + "/api"
    host, port = a.udp.rsplit(":", 1)

    post(api, "/demo/reset")
    lines = [t.encode() for _, _, t in itertools.islice(steady_lines(at(date.today(), 10, 12)), N_LINES)]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = [0]
    stop = threading.Event()

    def blast():
        # As fast as possible from one socket for the whole window (cycling through the pre-generated lines).
        for data in itertools.cycle(lines):
            if stop.is_set():
                break
            try:
                sock.sendto(data, (host, int(port)))
            except OSError:  # the local send buffer is full: let the OS drain it
                time.sleep(0.001)
                continue
            sent[0] += 1

    samples = []  # (t, sent, raw_total, normalized_total)
    t0 = time.monotonic()
    th = threading.Thread(target=blast, daemon=True)
    th.start()
    while time.monotonic() - t0 < DURATION_S:
        time.sleep(1)
        s = get(api, "/stats")
        samples.append((time.monotonic() - t0, sent[0], s["raw_total"], s["normalized_total"]))
    stop.set()
    th.join()
    total_sent = sent[0]
    # Pipeline catch-up: for each second's raw_total, how long until normalized_total reached it.
    series = [(t, raw, norm) for t, _, raw, norm in samples]
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        st = get(api, "/stats")
        series.append((time.monotonic() - t0, st["raw_total"], st["normalized_total"]))
        if st["normalized_total"] >= st["raw_total"]:
            break
        time.sleep(0.25)
    catch_up = {}
    for t, raw, _ in series[:len(samples)]:
        hit = next((t2 for t2, _, norm in series if t2 >= t and norm >= raw), None)
        if hit is not None:
            catch_up[t] = hit - t
    final = get(api, "/stats")
    after = [s for s in samples if s[0] > WARMUP_S]
    if len(after) < 3 or final["raw_total"] == 0:
        print("Benchmark failed: not enough samples; nothing written.")
        return 1
    raw_eps = statistics.median(b[2] - a_[2] for a_, b in zip(after, after[1:]))
    norm_eps = statistics.median(b[3] - a_[3] for a_, b in zip(after, after[1:]))
    if raw_eps <= 0:
        print(f"Benchmark failed: nothing was received after the warm-up ({final['raw_total']} of {total_sent}); "
              "nothing written. On Docker Desktop, run it inside the api container (see docs).")
        return 1
    lags = sorted(catch_up.values())
    p95 = f"{lags[min(len(lags) - 1, int(0.95 * len(lags)))]:.1f}" if lags else "> 60"
    loss = total_sent - final["raw_total"]
    row = (f"| {datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()} | {raw_eps:.0f} | {norm_eps:.0f} | {loss} of {total_sent} | {p95} | "
           f"{machine()} |\n")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        out.write_text("# BENCHMARKS\n\nMeasured by `make bench` (bench/load_test.py). Never estimated.\n\n" + HEADER,
                       encoding="utf-8")
    with open(out, "a", encoding="utf-8") as f:
        f.write(row)
    print(row.strip())
    post(api, "/demo/reset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
