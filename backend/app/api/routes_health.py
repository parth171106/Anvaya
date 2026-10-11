from fastapi import APIRouter

from app.api.deps import C
from app.api.schemas import Health, Stats

router = APIRouter(prefix="/api")
OK = {"ok", "ready", "air_gapped"}


@router.get("/health", response_model=Health)
async def health(c: C):
    comps = {}
    try:
        c.repo.con.execute("SELECT 1").fetchone()
        comps["database"] = {"status": "ok", "detail": "WAL"}
    except Exception as e:
        comps["database"] = {"status": "error", "detail": type(e).__name__}
    comps["vault"] = {"status": "error" if c.store.closed else "ok", "detail": f"{c.store.segment} · 64 MiB max"}
    last = c.repo.last_batch()
    top = last["batch_id"] if last else 0
    comps["ledger"] = {"status": "ok", "detail": f"last batch {top}" if last else "no batches yet"}
    agree = sum(1 for w in c.witnesses if w.last_batch() == top)
    comps["witnesses"] = {"status": "ok" if agree == len(c.witnesses) else "degraded", "ok_count": agree,
                          "total": len(c.witnesses)}
    comps["llm"] = {"status": "ready" if await c.llm.ready() else "fallback", "model": c.cfg.ollama_model}
    comps["network"] = c.network_status()
    if c.restarted:
        comps["monitors"] = {"status": "restarted", "detail": ", ".join(sorted(c.restarted))}
    status = "ok" if all(v["status"] in OK for v in comps.values()) else "degraded"
    return {"status": status, "demo_mode": c.cfg.demo_mode, "version": "1.0.0", "components": comps}


@router.get("/stats", response_model=Stats)
async def stats(c: C):
    return c.stats()
