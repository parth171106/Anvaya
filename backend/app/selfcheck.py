"""`make offline-test`: run the golden path in-process inside `docker run --network none` (TRD.md §15 item 4).
Prints one line per check, then PASS (exit 0) or FAIL (exit 1)."""
import asyncio
import sys
import time

import httpx

from app.core import config
from app.main import create_app

Q1 = "What did 10.2.4.18 do in the last hour?"


class Checks:
    def __init__(self):
        self.failed = 0
        self.summary: list[str] = []

    def __call__(self, name: str, ok: bool, got="") -> None:
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  ({got})" if not ok else ""), flush=True)
        self.failed += not ok


async def until(pred, timeout_s: float, step: float = 0.25):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if v := await pred():
            return v
        await asyncio.sleep(step)
    return None


async def run() -> int:
    cfg = config.load()
    check = Checks()
    app = create_app(cfg)
    async with app.router.lifespan_context(app):
        c = app.state.c
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://selfcheck",
                                     timeout=30) as api:
            await api.post("/api/demo/reset")
            r = await api.post("/api/demo/scenario/start", json={"speed": 40})
            check("scenario starts at 40x", r.status_code == 202, r.text)

            async def steady():
                return c.clock.phase == "steady" and c.queue.empty()
            await until(steady, 60)
            await asyncio.sleep(1.5)
            scripted = c.repo.con.execute("SELECT COUNT(*) FROM events WHERE time < ?", (c.clock.steady_ms,)).fetchone()[0]
            raw = c.repo.con.execute("SELECT COUNT(*) FROM raw_events WHERE received_at < ?",
                                     (c.clock.steady_ms,)).fetchone()[0]
            check("207 scripted raw records over loopback UDP", raw == 207, raw)
            check.summary.append(f"{raw} raw")
            check("207 normalized, 0 quarantined", scripted == 207 and c.repo.quarantine_total() == 0, scripted)

            inc = (await api.get("/api/incidents")).json()["items"]
            check("exactly 1 incident, risk 95", [(i["incident_id"], i["risk"]) for i in inc] == [("inc-0001", 95)], inc)
            check.summary.append(f"{len(inc)} incident (risk {inc[0]['risk'] if inc else '-'})")

            v = (await api.post("/api/ledger/verify")).json()
            check("verify -> verified", v["verdict"] == "verified", v["verdict"])
            check.summary.append("verify ok" if v["verdict"] == "verified" else f"verify {v['verdict']}")
            t = await api.post("/api/demo/tamper")
            v = (await api.post("/api/ledger/verify")).json()
            fr = v["failed_records"]
            check("tamper -> exactly 1 failed record at byte 153",
                  t.status_code == 200 and v["verdict"] == "tampered" and len(fr) == 1
                  and fr[0]["first_diff_offset"] == 153, v)
            check.summary.append("tamper caught" if v["verdict"] == "tampered" else "tamper missed")
            await api.post("/api/demo/reseal")
            v = (await api.post("/api/ledger/verify")).json()
            check("reseal -> witness_mismatch", v["verdict"] == "witness_mismatch", v["verdict"])
            check.summary.append("reseal caught" if v["verdict"] == "witness_mismatch" else "reseal missed")

            q = (await api.post("/api/search", json={"question": Q1})).json()
            check("Q1 -> 17 rows from the template engine", q.get("row_count") == 17 and q.get("engine") == "template",
                  {k: q.get(k) for k in ("row_count", "engine")})
            check.summary.append(f"Q1 {q.get('row_count')} rows")

            await api.post("/api/demo/inject-unknown")

            async def quarantined():
                g = (await api.get("/api/quarantine")).json()["groups"]
                return g[0]["group_id"] if g and g[0]["count"] == 20 else None
            gid = await until(quarantined, 10)
            check("unknown format -> 20 quarantined", gid is not None)
            d = await api.post("/api/parsers/drafts", json={"group_id": gid})
            did = d.json().get("draft_id") if d.status_code == 201 else None
            check("cached draft available", did is not None, d.text[:200])
            if did:
                t = (await api.post(f"/api/parsers/drafts/{did}/test")).json()
                check("draft gates 6/6, 20/20, 20/20, 20/20", t.get("promotable") is True, t.get("failures"))
                a = await api.post(f"/api/parsers/drafts/{did}/approve", json={"approved_by": "selfcheck"})

                async def replayed():
                    return (await api.get("/api/quarantine")).json()["total"] == 0
                ok = a.status_code == 200 and await until(replayed, 10)
                n = c.repo.con.execute("SELECT COUNT(*) FROM events WHERE device='br01'").fetchone()[0]
                check("approve -> 20 replayed", bool(ok) and n == 20, n)
                check.summary.append(f"br01 {n} replayed")
            await api.post("/api/demo/reset")
    verdict = "PASS" if check.failed == 0 else f"FAIL ({check.failed} checks)"
    print(f"selfcheck: {' · '.join(check.summary)} · {verdict}", flush=True)
    print(verdict, flush=True)
    return 0 if check.failed == 0 else 1


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
