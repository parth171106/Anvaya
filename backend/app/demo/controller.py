"""Demo controller (APP_FLOW.md FL-03, FL-06, FL-08, FL-09, FL-11). Only reachable when ANVAYA_DEMO_MODE=1."""
import asyncio
import logging
import shutil
import time

from app.ocsf.lineage import field_at
from app.vault.ledger import TAMPER_OFFSET, TAMPER_VALUE
from generator.br01 import build_br01_lines
from generator.scenario import run as run_generator
from generator.sinks import UdpSink

log = logging.getLogger("anvaya.demo")
SPEEDS = (10, 20, 40)
WIPE = ("vault", "witness", "outbox", "lake", "packs")


class DemoConflict(Exception):
    pass


class DemoController:
    def __init__(self, c):
        self.c = c
        self.task: asyncio.Task | None = None
        self.sink: UdpSink | None = None
        self.stop_flags: dict[str, bool] = {}
        self.tampered = self.resealed = self.unknown_injected = False
        self.tamper_info: dict | None = None
        c.clock.on_change = self.publish_state

    # ---- state ----------------------------------------------------------------------------------------------------
    def state(self) -> dict:
        clk = self.c.clock
        return {"demo_mode": True, "phase": clk.phase, "speed": clk.speed,
                "silenced": sorted(d for d, s in self.stop_flags.items() if s), "tampered": self.tampered,
                "resealed": self.resealed, "unknown_injected": self.unknown_injected,
                "send_errors": self.sink.errors if self.sink else 0,
                "clock": {"now_ms": clk.now_ms(), "label": clk.label()}}

    def publish_state(self, **extra) -> None:
        s = self.state()
        self.c.publish("demo.state", {k: s[k] for k in ("phase", "speed", "silenced", "tampered", "resealed",
                                                        "unknown_injected")} | extra)

    # ---- scenario -------------------------------------------------------------------------------------------------
    def start(self, speed: int | None = None) -> dict:
        if self.c.clock.phase != "idle":
            raise DemoConflict("Simulation already running. Press 0 twice to reset.")
        if speed is not None and speed not in SPEEDS:
            raise ValueError("speed must be 10, 20 or 40")
        self.c.clock.start(speed=speed)
        self.sink = UdpSink("127.0.0.1", self.c.cfg.syslog_udp_port)
        self.task = asyncio.create_task(run_generator(self.c.clock, self.sink, self.stop_flags), name="generator")
        self.publish_state()
        return {"phase": "scripted", "speed": self.c.clock.speed, "scripted_lines": 207}

    def set_speed(self, speed: int) -> dict:
        if speed not in SPEEDS:
            raise ValueError("speed must be 10, 20 or 40")
        self.c.clock.set_speed(speed)
        self.publish_state()
        return {"speed": speed}

    def inject_unknown(self) -> dict:
        if self.unknown_injected:
            raise DemoConflict("The unknown source was already injected.")
        # Same records and transport label as POST /api/ingest; called in-process instead of over loopback HTTP.
        for line in build_br01_lines(self.c.clock.now_ms()):
            self.c.ingest(line.encode("utf-8"), "http", "127.0.0.1")
        self.unknown_injected = True
        self.publish_state()
        return {"lines": 20}

    def silence(self, device: str, silent: bool) -> dict:
        self.stop_flags[device] = silent
        self.publish_state()
        return {"device": device, "silent": silent}

    # ---- integrity ------------------------------------------------------------------------------------------------
    def tamper(self) -> dict:
        if self.tamper_info:
            return self.tamper_info
        target = self.c.ledger.tamper_target()
        if target is None or target.batch_id is None:
            raise DemoConflict("Wait for the firewall allow event to be sealed, then try again.")
        before = self.c.store.read(target.raw_id)[TAMPER_OFFSET:TAMPER_OFFSET + 1].decode("latin-1")
        self.c.store.overwrite_byte_for_demo(target.raw_id, TAMPER_OFFSET, TAMPER_VALUE)
        ev = self.c.repo.event_evidence(target.raw_id)
        field = (field_at(ev[1], TAMPER_OFFSET) if ev else None) or "dst_endpoint.ip"
        self.tamper_info = {"raw_id": target.raw_id, "offset": TAMPER_OFFSET, "from": before,
                            "to": chr(TAMPER_VALUE), "field": field}
        self.tampered = True
        self.c.repo.audit(self.c.clock.now_ms(), "presenter", "demo.tamper", target.raw_id, self.tamper_info)
        self.publish_state()
        return self.tamper_info

    def reseal(self) -> dict:
        if not self.tampered:
            raise DemoConflict("Simulate tamper first.")
        target = self.c.ledger.tamper_target()
        batches = self.c.ledger.reseal_from(target.batch_id)
        self.resealed = True
        self.c.repo.audit(self.c.clock.now_ms(), "presenter", "demo.reseal", str(target.batch_id),
                          {"batches": batches})
        self.publish_state()
        return {"resealed_batches": batches, "note": "Primary ledger re-signed; witness stores untouched."}

    # ---- reset (FL-11) --------------------------------------------------------------------------------------------
    async def reset(self) -> dict:
        t0 = time.perf_counter()
        c = self.c
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except BaseException:
                pass
            self.task = None
        if self.sink:
            self.sink.close()
            self.sink = None
        while not c.queue.empty():
            c.queue.get_nowait()
        c.close_stores()
        d = c.cfg.data_dir
        targets = [d / n for n in WIPE] + [d / f"anvaya.db{s}" for s in ("", "-wal", "-shm")]
        for path in targets:
            for attempt in range(3):  # a file can be briefly locked on Windows
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    elif path.exists():
                        path.unlink()
                    break
                except OSError:
                    if attempt == 2:
                        raise RuntimeError(f"Reset failed: {path}")
                    await asyncio.sleep(0.2)
        c.clock.reset()
        c.open_stores()
        c.replays.reset()
        c.bus.clear()
        self.stop_flags.clear()
        self.tampered = self.resealed = self.unknown_injected = False
        self.tamper_info = None
        c.repo.audit(c.clock.now_ms(), "presenter", "demo.reset")
        asyncio.create_task(c.llm.warmup(), name="llm-warmup")
        self.publish_state(reset=True)
        return {"ok": True, "took_ms": round((time.perf_counter() - t0) * 1000)}
