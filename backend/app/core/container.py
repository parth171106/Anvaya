"""Builds and owns every service. Implementations are picked from Config (TRD.md §4)."""
import logging
import time

from app.aiparser.drafts import DraftService
from app.aiparser.sources import CachedDraftSource, LlmDraftSource
from app.core.clock import ScenarioClock, WallClock
from app.core.config import Config
from app.core.models import NormalizedEvent, RawMeta, RawRecord
from app.core.queue import InProcQueue
from app.delivery.siem import FileSink, SiemForwarder
from app.ingest.vetting import vet
from app.intel.correlate import Correlator
from app.intel.silence import SilenceMonitor
from app.parsers.registry import PackRegistry
from app.pipeline.replay import ReplayManager
from app.pipeline.worker import PipelineWorker
from app.search.llm import OllamaClient
from app.search.nl2sql import SearchService
from app.storage.sqlite_repo import SqliteRepository
from app.stream.bus import EventBus
from app.vault.keys import load_or_create_keys
from app.vault.ledger import Ledger
from app.vault.store import SegmentRawStore
from app.vault.witness import InProcessWitness

log = logging.getLogger("anvaya")
WITNESSES = ("witness-ntro", "witness-certin")


class Container:
    def __init__(self, cfg: Config, enums=None, validate=None):
        if enums is None or validate is None:  # fail fast if the vendored OCSF schema is missing
            from app.ocsf.enums import Enums
            from app.ocsf.validate import OcsfValidator
            enums, validate = enums or Enums(), validate or OcsfValidator()
        self.cfg, self.enums, self.validate = cfg, enums, validate
        self.clock = ScenarioClock() if cfg.demo_mode else WallClock()
        self.keys = load_or_create_keys(cfg.data_dir / "keys")
        self.bus = EventBus()
        self.llm = OllamaClient(cfg.ollama_url, cfg.ollama_model)
        self.queue = InProcQueue()  # lives as long as the container: the worker awaits it across demo resets
        self.replays = ReplayManager(self.queue, lambda e, data: self.publish(e, data))
        self.worker = PipelineWorker(self)
        self.restarted: set[str] = set()   # background tasks the supervisor had to restart
        self.network = {"status": "not_checked"}
        self.open_stores()
        if cfg.demo_mode:
            from app.demo.controller import DemoController
            self.demo = DemoController(self)

    def open_stores(self) -> None:
        d = self.cfg.data_dir
        emit = lambda e, data: self.publish(e, data)  # late-bound so the bus (or a test) can be swapped
        self.repo = SqliteRepository(d / "anvaya.db")
        self.store = SegmentRawStore(d / "vault", self.clock, index=self.repo.raw_records(), demo=self.cfg.demo_mode)
        self.witnesses = [InProcessWitness(n, d / "witness" / f"{n}.db", self.keys[n]) for n in WITNESSES]
        self.ledger = Ledger(self.repo, self.store, self.keys, self.witnesses, self.clock, self.cfg, emit)
        self.registry = PackRegistry(extra_dir=d / "packs")
        self.correlator = Correlator(self.repo, emit)
        self.silence = SilenceMonitor(self.repo, emit, self.cfg.silence_min_seconds)
        self.siem = SiemForwarder(FileSink(d / "outbox" / "siem-forward.ndjson"), self.clock)
        self.event_hooks = [self.correlator.on_batch, self.silence.on_events, self.siem.on_batch]
        self.search = SearchService(self.repo, self.llm, self.clock, self.cfg)
        self.drafts = DraftService(self, CachedDraftSource() if self.cfg.demo_mode else LlmDraftSource(self.llm))
        with self.repo.tx():
            for p in self.registry.packs:
                self.repo.upsert_parser(p, "builtin" if p.origin == "builtin" else "ai_draft")

    def network_status(self) -> dict:
        return dict(self.network)

    def publish(self, event: str, data) -> None:
        self.bus.publish(event, data)

    def close_stores(self) -> None:
        self.siem.sink.close()
        self.store.close()
        for w in self.witnesses:
            w.close()
        self.repo.close()

    def ingest(self, data: bytes, transport: str, peer_ip: str) -> RawRecord:
        """FL-01 steps 2–6: vet → vault → raw_events → sealer → queue."""
        flags, encoding = vet(data)
        rec = self.store.append(data, RawMeta(transport=transport, peer_ip=peer_ip, flags=flags, encoding=encoding))
        self.repo.insert_raw(rec)
        self.ledger.add(rec)
        self.queue.put_nowait(rec.raw_id)
        return rec

    def stats(self) -> dict:
        """API 2 / SSE stats.tick."""
        n = self.repo.counts()
        parsed, quarantined = n.pop("roundtrip_ok"), n["quarantined_total"]
        n["parse_coverage_pct"] = round(100 * parsed / (parsed + quarantined), 1) if parsed + quarantined else None
        n["ingest_rate_eps"] = round(self.repo.raw_received_since_wall(int(time.time() * 1000) - 10_000) / 10, 1)
        n["cosigned_batches"] = self.repo.cosigned_batches()
        n["last_bench"] = self.last_bench
        n["clock"] = {"now_ms": self.clock.now_ms(), "label": self.clock.label(), "display_tz": self.cfg.display_tz}
        return n

    last_bench = None  # set from docs/BENCHMARKS.md when present (M11)

    def on_events(self, events: list[NormalizedEvent]) -> None:
        for hook in self.event_hooks:
            try:
                hook(events)
            except Exception:  # a hook failure never affects ingest; the next batch retries
                log.exception("event hook %s failed", getattr(hook, "__qualname__", hook))
