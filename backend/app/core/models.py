from typing import Literal
from pydantic import BaseModel

DeviceId = str
FormatId = str
Severity = Literal["Informational", "Low", "Medium", "High", "Critical"]
QuarantineReason = Literal["no_fingerprint", "no_rule", "parse_error", "schema_invalid", "roundtrip_fail"]

class RawMeta(BaseModel):
    transport: Literal["udp", "tcp", "http", "file"]; peer_ip: str; flags: list[str]; encoding: Literal["utf-8", "binary"]

class RawRecord(BaseModel):
    raw_id: str; seq: int; raw_sha256: str; size: int; segment: str; offset: int
    received_at: int; wall_received_at: int; meta: RawMeta; batch_id: int | None = None

class LineageEntry(BaseModel):
    path: str; spans: list[tuple[int, int]]; derived: bool

class RoundTrip(BaseModel):
    ok: bool; value_check: bool; coverage: float; dropped: int

class AnvayaMeta(BaseModel):
    format: FormatId; vendor: str; product: str; device: str; parser: str; rule_id: str
    parse_confidence: int; confidence_breakdown: dict[str, float]
    source_timezone: str; device_time_raw: str; clock_skew_s: int
    roundtrip: RoundTrip; lineage: list[LineageEntry]

class NormalizedEvent(BaseModel):
    event_id: str; raw_id: str; seq: int; ocsf: dict; anvaya: AnvayaMeta
    # flat columns are derived from ocsf + anvaya by storage.flatten()

class EventSummary(BaseModel):
    event_id: str; raw_id: str; seq: int; time: int; device: str; vendor: str; format: str
    class_uid: int; class_name: str; activity_name: str
    src_ip: str | None; src_port: int | None; dst_ip: str | None; dst_port: int | None
    protocol: str | None; direction: str | None; user_name: str | None
    action: str | None; status: str | None; severity: Severity; title: str | None
    parse_confidence: int; batch_id: int | None; flags: list[str]

class FailedRecord(BaseModel):
    raw_id: str; event_id: str | None; seq: int; batch_id: int; device: str | None; time: int | None
    first_diff_offset: int | None; changed: dict[str, str] | None; field: str | None

class LedgerVerifyResult(BaseModel):
    verdict: Literal["verified", "tampered", "witness_mismatch"]
    checked_records: int; checked_batches: int; took_ms: int
    failed_records: list[FailedRecord]
    failed_batches: list[dict]          # {"batch_id": int, "reason": "leaf_mismatch"|"root_mismatch"|"chain_break"|"bad_signature"}
    witness_status: list[dict]          # {"name": str, "agree": bool, "mismatched_batches": list[int]}

class IncidentWorkflow(BaseModel):
    state: Literal['new', 'investigating', 'resolved'] = 'new'
    controlled_test: bool = False
    version: int = 0


class IncidentSummary(BaseModel):
    incident_id: str; title: str; attacker_ip: str; target_ip: str | None; risk: int
    level: Literal["Low", "Medium", "High"]; stages: list[Literal["recon", "credential", "access"]]
    devices: list[str]; event_count: int; first_time: int; last_time: int; status: Literal["open", "closed"]
    workflow: IncidentWorkflow = IncidentWorkflow()

class SearchResult(BaseModel):
    query_id: str | None = None
    result_type: Literal["events", "incidents"] = "events"
    incidents: list[IncidentSummary] = []
    question: str; engine: Literal["llm", "template"]; model: str | None; sql: str; params: dict
    clock_caption: str; columns: list[str]; rows: list[list]; row_count: int; took_ms: int

# Not in BACKEND_SCHEMA.md §6.1, but imported by TRD.md §4 interfaces. Mirrors the API 4 query params.
class EventFilter(BaseModel):
    limit: int = 50; before_seq: int | None = None; device: str | None = None
    format: str | None = None; class_uid: int | None = None; q: str | None = None
