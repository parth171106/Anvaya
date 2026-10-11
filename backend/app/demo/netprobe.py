"""DEMO_MODE network-route probe (TRD.md §15 item 3): TCP connect only, no payload, every 10 s."""
import asyncio
import time

TARGETS = (("1.1.1.1", 443), ("9.9.9.9", 443))


async def _reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        w.close()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


async def probe() -> dict:
    results = await asyncio.gather(*(_reachable(h, p) for h, p in TARGETS))
    return {"status": "external_route" if any(results) else "air_gapped", "checked_at": int(time.time() * 1000)}


async def probe_loop(c, interval_s: float = 10) -> None:
    while True:
        c.network = await probe()
        await asyncio.sleep(interval_s)
