import asyncio
import contextlib
import json
import logging
import sys
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api import (errors, routes_delivery, routes_demo, routes_events, routes_health, routes_incidents, routes_ledger,
                     routes_parsers, routes_search, routes_sources, routes_stream)
from app.api.errors import not_found
from app.api import routes_accounts, routes_legal, routes_recovery, routes_alerts
from app.api.deps import C
from app.auth import Auth, AuthMiddleware, router as auth_router
from app.core import config
from app.core.container import Container
from app.core.workspaces import Workspaces
from app.ingest import http as ingest_http
from app.ingest.udp import start_udp

log = logging.getLogger("anvaya")


class JsonLines(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        out = {"ts": int(r.created * 1000), "level": r.levelname.lower(), "component": r.name, "msg": r.getMessage()}
        if r.exc_info:
            out["error"] = self.formatException(r.exc_info).splitlines()[-1]
        return json.dumps(out)


def setup_logging() -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonLines())
    root = logging.getLogger("anvaya")
    root.handlers[:] = [h]
    root.setLevel(logging.INFO)
    root.propagate = False


async def supervise(c: Container, name: str, fn) -> None:
    """Run a background loop forever; if it crashes, log it, mark it restarted (shown in /api/health) and restart."""
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s crashed; restarting", name)
            c.restarted.add(name)
            await asyncio.sleep(1)


def every(seconds: float, fn):
    async def loop():
        while True:
            await asyncio.sleep(seconds)
            fn()
    return loop


def background_tasks(c: Container) -> list[asyncio.Task]:
    loops = {
        "pipeline_worker": c.worker.run,
        "ledger_sealer": every(0.25, lambda: c.ledger.tick()),
        "silence_monitor": every(1.0, lambda: c.silence.tick()),
        "stats": every(1.0, lambda: c.publish("stats.tick", c.stats())),
        "alert_delivery": lambda: c.alerts.run(),
    }
    if c.cfg.demo_mode:
        from app.demo.netprobe import probe_loop
        loops["netprobe"] = lambda: probe_loop(c)
    return [asyncio.create_task(supervise(c, name, fn), name=name) for name, fn in loops.items()]


def create_app(cfg: config.Config | None = None, container_factory=Container) -> FastAPI:
    cfg = cfg or config.load()
    auth = Auth(cfg)
    setup_logging()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        c = app.state.c = container_factory(cfg)
        c.last_bench = load_last_bench() if cfg.demo_mode else None
        try:
            udp = None if auth.enabled else await start_udp(c.ingest, cfg.syslog_udp_port, cfg.syslog_bind_host)
        except Exception:
            c.close_stores()
            raise
        tasks = background_tasks(c) + [asyncio.create_task(c.llm.warmup(), name="llm-warmup")]
        workspaces = app.state.workspaces = Workspaces(cfg, c, container_factory, background_tasks)
        if auth.accounts:
            for account in auth.accounts.list():
                if not account["disabled"]:
                    workspaces.get(account["id"])
        log.info("ANVAYA ready (demo_mode=%s, data=%s)", cfg.demo_mode, cfg.data_dir)
        try:
            yield
        finally:
            if udp is not None:
                udp.close()
            for t in tasks:
                t.cancel()
            if cfg.demo_mode and c.demo.task:
                c.demo.task.cancel()
            await asyncio.gather(*tasks, *([c.demo.task] if cfg.demo_mode and c.demo.task else []), return_exceptions=True)
            await workspaces.close()
            c.close_stores()
            if auth.accounts:
                auth.accounts.close()

    app = FastAPI(title="ANVAYA", version="1.0.0", lifespan=lifespan)
    app.state.auth = auth
    app.add_middleware(CORSMiddleware, allow_origins=[] if auth.enabled else ["http://localhost:8080", "http://localhost:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(AuthMiddleware, auth=auth)
    errors.install(app)
    app.include_router(auth_router)
    app.include_router(routes_accounts.router)
    app.include_router(routes_recovery.router)
    app.include_router(routes_legal.router)
    app.include_router(routes_alerts.router)
    app.include_router(ingest_http.router)
    for r in (routes_health, routes_events, routes_ledger, routes_sources, routes_parsers, routes_incidents,
              routes_search, routes_delivery, routes_demo, routes_stream):
        app.include_router(r.router)

    @app.get("/api/ready")
    async def ready():
        app.state.c.repo.con.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.get("/api/raw/{raw_id}")
    async def raw(raw_id: str, c: C):
        rec = c.repo.get_raw(raw_id)  # stored hash comes from raw_events (what verify compares against)
        if not rec:
            raise not_found("Raw record")
        return Response(c.store.read(raw_id), media_type="application/octet-stream",
                        headers={"X-Raw-Sha256-Stored": rec.raw_sha256, "X-Raw-Seq": str(rec.seq)})

    return app


def load_last_bench():
    """The newest measured row of docs/BENCHMARKS.md, if `make bench` has run (TRD.md API 2). Never estimated."""
    from pathlib import Path
    for f in (Path("docs/BENCHMARKS.md"), Path(__file__).parents[2] / "docs" / "BENCHMARKS.md"):
        if f.exists():
            rows = [ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")]
            if rows:
                cells = [x.strip() for x in rows[-1].strip("|").split("|")]
                try:  # | date | eps | normalized eps | loss | p95 | machine |
                    measured = int(time.mktime(time.strptime(cells[0][:10], "%Y-%m-%d")) * 1000)
                    return {"eps": float(cells[1]), "machine": cells[-1], "measured_at": measured}
                except (ValueError, IndexError):
                    return None
    return None
