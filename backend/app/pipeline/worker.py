"""FL-01 steps 7–16: raw bytes → fingerprint → parse → OCSF → validate → round-trip → score → store → publish."""
import asyncio
import logging
from dataclasses import dataclass, field

from app.core.ids import event_id, group_id
from app.core.models import AnvayaMeta, LineageEntry, NormalizedEvent, RoundTrip
from app.ingest.vetting import MAX_PARSE_BYTES
from app.ocsf.confidence import score
from app.ocsf.lineage import ordered, to_bytes
from app.ocsf.mapper import MappingError, get_path, map_to_ocsf
from app.ocsf.roundtrip import check_roundtrip
from app.parsers.engine import ParseFailure, parse_with_pack
from app.parsers.shape import shape
from app.parsers.syslog_header import ByteOffsets, split

CLOCK_SKEW_FLAG_S = 300


@dataclass
class Outcome:
    event: NormalizedEvent | None = None
    reason: str | None = None          # quarantine reason when event is None (or roundtrip_fail alongside an event)
    detail: str | None = None
    shape: tuple | None = None         # (signature, delimiter, field_count, first_token) for quarantined records
    flags: list[str] = field(default_factory=list)


def normalize(data: bytes, raw_id: str, seq: int, received_at: int, encoding: str, registry, enums, validate,
              pack=None) -> Outcome:
    data = data[:MAX_PARSE_BYTES]
    text = data.decode("utf-8", "surrogateescape")
    hs = split(text)
    pack = pack or registry.detect(hs, text)
    if pack is None:
        return Outcome(reason="no_fingerprint", detail="no parser pack detects this format", shape=shape(text))
    try:
        res = parse_with_pack(pack, text, hs)
        eid = event_id(raw_id)
        mapped = map_to_ocsf(res, text, eid, enums)
    except ParseFailure as e:
        return Outcome(reason=e.reason, detail=e.detail, shape=shape(text))
    except MappingError as e:
        return Outcome(reason="parse_error", detail=str(e), shape=shape(text))
    ocsf = mapped.ocsf
    err = validate(ocsf)
    if err:
        return Outcome(reason="schema_invalid", detail=err, shape=shape(text))
    offsets = ByteOffsets(text)
    traces = to_bytes(ordered(mapped.traces), offsets)
    accounted = [offsets.span(s) for s in res.accounted]
    rt = check_roundtrip(data, encoding, traces, accounted, [v.name for v in res.values])
    names = [v.name for v in res.values]
    conf, breakdown = score(e=len(names), m=sum(1 for n in names if n in mapped.mapped_names),
                            r_present=sum(1 for p in pack.required if get_path(ocsf, p) is not None),
                            r_total=len(pack.required), t_ok=mapped.typed_ok, t_total=mapped.typed_total)
    skew = round(abs(ocsf["time"] - received_at) / 1000)
    flags = (["roundtrip_fail"] if not rt["ok"] else []) + (["clock_skew"] if skew > CLOCK_SKEW_FLAG_S else [])
    anvaya = AnvayaMeta(format=pack.format, vendor=pack.vendor, product=pack.product,
                        device=(ocsf.get("device") or {}).get("hostname", ""), parser=pack.id, rule_id=res.rule.id,
                        parse_confidence=conf, confidence_breakdown=breakdown, source_timezone=pack.source_timezone,
                        device_time_raw=mapped.original_time or "", clock_skew_s=skew, roundtrip=RoundTrip(**rt),
                        lineage=[LineageEntry(**t.public()) for t in traces])
    ev = NormalizedEvent(event_id=eid, raw_id=raw_id, seq=seq, ocsf=ocsf, anvaya=anvaya)
    return Outcome(event=ev, reason=None if rt["ok"] else "roundtrip_fail",
                   detail=None if rt["ok"] else f"round-trip {rt}", shape=None if rt["ok"] else shape(text), flags=flags)


log = logging.getLogger("anvaya.pipeline")
BATCH_MAX, BATCH_WAIT_S = 32, 0.1


class PipelineWorker:
    """Consumes raw_ids from the queue in batches of ≤ 32 or 100 ms, stores the results, then runs the hooks."""

    def __init__(self, c):
        self.c = c

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            batch = [await self.c.queue.get()]
            deadline = loop.time() + BATCH_WAIT_S
            while len(batch) < BATCH_MAX and (left := deadline - loop.time()) > 0:
                try:
                    batch.append(await asyncio.wait_for(self.c.queue.get(), left))
                except TimeoutError:
                    break
            self.process(batch)

    def drain(self) -> None:
        """Process everything queued right now (tests and the self-check)."""
        while not self.c.queue.empty():
            batch = []
            while not self.c.queue.empty() and len(batch) < BATCH_MAX:
                batch.append(self.c.queue.get_nowait())
            self.process(batch)

    def process(self, raw_ids: list[str]) -> list[NormalizedEvent]:
        c = self.c
        events, flags, quarantined = [], {}, []
        for rid in raw_ids:
            rec = c.repo.get_raw(rid)
            if rec is None:  # cleared by a reset while queued
                continue
            data = b""
            try:
                data = c.store.read(rid)
                out = normalize(data, rid, rec.seq, rec.received_at, rec.meta.encoding, c.registry, c.enums, c.validate)
            except Exception as e:  # one bad record never stops the worker
                log.exception("normalize failed for %s", rid)
                out = Outcome(reason="parse_error", detail=type(e).__name__,
                              shape=shape(data[:MAX_PARSE_BYTES].decode("utf-8", "surrogateescape")))
            if out.event:
                events.append(out.event)
                flags[rid] = out.flags
            if out.reason:
                quarantined.append((rec, out, data))
        with c.repo.tx():
            c.repo.insert_events(events, flags)
            for ev in events:
                if "roundtrip_fail" not in flags[ev.raw_id]:
                    c.repo.unquarantine(ev.raw_id)
            for rec, out, _ in quarantined:
                c.repo.quarantine(rec.raw_id, group_id(out.shape[0]), out.shape[0], out.reason, out.detail,
                                  rec.received_at)
        for s in c.repo.summaries([e.event_id for e in events]) if events else []:
            c.publish("event.normalized", s)
        for rec, out, data in quarantined:
            if not out.event:
                c.publish("event.quarantined", {
                    "raw_id": rec.raw_id, "seq": rec.seq, "time": rec.received_at, "group_id": group_id(out.shape[0]),
                    "reason": out.reason, "preview": data[:160].decode("utf-8", "replace")})
        parsed = {e.raw_id for e in events if "roundtrip_fail" not in flags[e.raw_id]}
        for rid in raw_ids:
            c.replays.on_processed(rid, rid in parsed)
        if events:
            c.on_events(events)
        return events
