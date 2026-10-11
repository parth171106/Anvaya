# BENCHMARKS

Measured by `make bench` (bench/load_test.py). Never estimated; a failed run writes nothing.

Method: reset, then 30 s of steady-phase syslog lines sent over UDP as fast as possible from one socket; `/api/stats`
polled every second. *Raw/normalized events/s* is the median per-second delta after a 5 s warm-up. *UDP loss* is
datagrams sent minus records received (the sender floods far faster than one receiver can take, so most are dropped
in the kernel by design). *p95 pipeline catch-up* is how long `normalized_total` took to reach each second's `raw_total`.

On Docker Desktop (Windows/macOS) run it inside the api container, because Docker Desktop's userland UDP port-forwarder
drops most datagrams before they reach the service:
`docker compose cp bench/load_test.py api:/srv/bench/load_test.py && docker compose exec api python /srv/bench/load_test.py --api http://127.0.0.1:8000 --udp 127.0.0.1:5514`.
On a Linux host, `make bench` measures through the published port directly.

| Date | Raw events/s (sustained) | Normalized events/s | UDP loss | p95 pipeline catch-up (s) | Machine |
|---|---|---|---|---|---|
| 2026-10-02 | 616 | 608 | 15202430 of 15221287 | 1.1 | 13th Gen Intel(R) Core(TM) i5-13500H · 16 cores · 7 GB RAM · Linux 5.15.167.4-microsoft-standard-WSL2 |
