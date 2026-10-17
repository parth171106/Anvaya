"""Pydantic response models for TRD.md §16 (shared shapes come from app.core.models)."""
from typing import Literal

from pydantic import BaseModel

from app.core.models import EventSummary, FailedRecord, IncidentSummary, SearchResult  # noqa: F401 (re-used shapes)


class Component(BaseModel, extra="allow"):
    status: str


class Health(BaseModel):
    status: Literal["ok", "degraded"]; demo_mode: bool; version: str; components: dict[str, Component]


class Bench(BaseModel):
    eps: float; machine: str; measured_at: int


class ClockInfo(BaseModel):
    now_ms: int; label: str; display_tz: str


class Stats(BaseModel):
    raw_total: int; normalized_total: int; quarantined_total: int; formats_detected: int
    parse_coverage_pct: float | None; ingest_rate_eps: float; sealed_records: int; sealed_batches: int
    cosigned_batches: int; open_incidents: int; sources_total: int; sources_silent: int
    last_bench: Bench | None; clock: ClockInfo


class IngestAccepted(BaseModel):
    accepted: int; raw_ids: list[str]; flagged: int


class EventPage(BaseModel):
    items: list[EventSummary]; next_before_seq: int | None


class RawView(BaseModel):
    raw_id: str; seq: int; size: int; encoding: str; flags: list[str]; transport: str; peer_ip: str
    received_at: int; raw_sha256: str; batch_id: int | None; text: str


class EventDetail(BaseModel):
    event_id: str; raw: RawView; ocsf: dict; anvaya: dict


class WitnessAgree(BaseModel):
    name: str; agree: bool


class RecordVerify(BaseModel):
    raw_id: str; ok: bool; seq: int; batch_id: int; leaf_index: int; sha256_stored: str; sha256_now: str
    audit_path: list[str]; root_ok: bool; signature_ok: bool; witnesses: list[WitnessAgree]
    first_diff_offset: int | None; changed: dict[str, str] | None; field: str | None


class BatchWitness(BaseModel):
    name: str; cosigned: bool


class Batch(BaseModel):
    batch_id: int; first_seq: int; last_seq: int; leaf_count: int; merkle_root: str; prev_head: str; head: str
    signature: str; sealed_at: int; resealed: bool; witnesses: list[BatchWitness]


class BatchPage(BaseModel):
    items: list[Batch]; primary_key_fingerprint: str


class FailedBatch(BaseModel):
    batch_id: int; reason: str


class WitnessVerdict(BaseModel):
    name: str; agree: bool; mismatched_batches: list[int]


class VerifyResult(BaseModel):
    verdict: Literal["verified", "tampered", "witness_mismatch"]; checked_records: int; checked_batches: int
    took_ms: int; failed_records: list[FailedRecord]; failed_batches: list[FailedBatch]
    witness_status: list[WitnessVerdict]; pending_seal: int = 0


class WitnessInfo(BaseModel):
    name: str; label: str; pubkey_fingerprint: str; last_cosigned_batch: int; status: str


class Items(BaseModel):
    items: list


class Source(BaseModel):
    device: str; vendor: str; product: str; format: str; parser: str; first_seen: int; last_seen: int
    events_total: int; rate_epm: float; expected_gap_s: float | None; status: Literal["learning", "active", "silent"]
    silent_for_s: int


class QuarantineGroup(BaseModel):
    group_id: str; shape_signature: str; shape_label: str; reason: str; count: int; first_seen: int; last_seen: int
    transport: str; peer_ip: str; sample_lines: list[str]


class Quarantine(BaseModel):
    total: int; groups: list[QuarantineGroup]


class ReplayStarted(BaseModel):
    replay_id: str; queued: int


class ParserInfo(BaseModel):
    name: str; version: str; status: str; origin: str; format: str; approved_by: str | None
    approved_at: int | None; roundtrip_pass_rate: float | None; events_parsed: int


class Draft(BaseModel):
    draft_id: str; group_id: str; status: str; origin: str; model: str | None; generated_at: int | None; yaml: str
    train_count: int; holdout_count: int; holdout_indexes: list[int]


class DraftView(Draft):
    test: dict | None


class Passed(BaseModel):
    passed: int; total: int


class RoundTripGate(Passed):
    min_coverage: float


class DraftTest(BaseModel):
    draft_id: str; promotable: bool; holdout: Passed; all: Passed; roundtrip: RoundTripGate; ocsf_valid: Passed
    failures: list[dict]; samples: list[dict]


class Approved(BaseModel):
    parser: dict; replay_id: str; queued: int


class Rejected(BaseModel):
    draft_id: str; status: str


class Stage(BaseModel):
    stage: str; label: str; first_time: int; last_time: int; devices: list[str]; event_count: int; headline: str
    event_ids: list[str]


class IncidentDetail(IncidentSummary):
    stages_detail: list[Stage]; risk_breakdown: dict[str, int]; events: list[EventSummary] = []
    explanation: str = ""
    recommended_action: str = ""
    activity: list[dict] = []
    ssh_finding: bool = False
    ssh_context: list[EventSummary] = []
    ssh_context_total: int = 0


class DemoState(BaseModel, extra="allow"):
    demo_mode: bool


class Ok(BaseModel):
    ok: bool; took_ms: int


class Started(BaseModel):
    phase: str; speed: int; scripted_lines: int


class Tamper(BaseModel):
    raw_id: str; offset: int; field: str
    model_config = {"extra": "allow"}  # carries "from"/"to" (reserved words in Python)


class Reseal(BaseModel):
    resealed_batches: list[int]; note: str


class Siem(BaseModel):
    mode: Literal["file_sink"]; target: str; forwarded: int; last_forwarded: int | None; last_payload: str | None
    status: str


class LakeExport(BaseModel):
    file: str; rows: int; bytes: int; created: int


class DeliveryStatus(BaseModel):
    siem: Siem; lake: dict[str, list[LakeExport]]; retention: dict[str, bool]


class ParquetExport(BaseModel):
    file: str; rows: int; duckdb_rows: int; bytes: int; took_ms: int


class RetentionSource(BaseModel):
    device: str; oldest: int; newest: int; records: int; sealed: bool


class RetentionReport(BaseModel):
    generated: int; statement: str; retention_target_days: int; sources: list[RetentionSource]
    ledger: dict[str, str | int | None]; note: str
