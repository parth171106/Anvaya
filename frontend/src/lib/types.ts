// Exactly BACKEND_SCHEMA.md §6.2 (extracted verbatim), plus the few API shapes it doesn't list, at the end.
export type DeviceId = string;
export type FormatId = string;
export type Severity = 'Informational' | 'Low' | 'Medium' | 'High' | 'Critical';
export type DemoPhase = 'idle' | 'scripted' | 'steady';
export type QuarantineReason = 'no_fingerprint' | 'no_rule' | 'parse_error' | 'schema_invalid' | 'roundtrip_fail';

export interface EventSummary {
  event_id: string; raw_id: string; seq: number; time: number; device: DeviceId; vendor: string; format: FormatId;
  class_uid: 4001 | 2004 | 3002; class_name: string; activity_name: string;
  src_ip: string | null; src_port: number | null; dst_ip: string | null; dst_port: number | null;
  protocol: string | null; direction: string | null; user_name: string | null;
  action: 'Allowed' | 'Denied' | null; status: 'Success' | 'Failure' | null; severity: Severity; title: string | null;
  parse_confidence: number; batch_id: number | null; flags: string[];
}
export interface LineageEntry { path: string; spans: [number, number][]; derived: boolean; }
export interface EventDetail {
  event_id: string;
  raw: { raw_id: string; seq: number; size: number; encoding: 'utf-8' | 'binary'; flags: string[]; transport: string;
         peer_ip: string; received_at: number; raw_sha256: string; batch_id: number | null; text: string };
  ocsf: Record<string, unknown>;
  anvaya: { format: FormatId; vendor: string; product: string; device: DeviceId; parser: string; rule_id: string;
            parse_confidence: number; confidence_breakdown: { required: number; typed: number; mapped: number };
            source_timezone: string; device_time_raw: string; clock_skew_s: number;
            roundtrip: { ok: boolean; value_check: boolean; coverage: number; dropped: number }; lineage: LineageEntry[] };
}
export interface RecordVerifyResult {
  raw_id: string; ok: boolean; seq: number; batch_id: number; leaf_index: number; sha256_stored: string; sha256_now: string;
  audit_path: string[]; root_ok: boolean; signature_ok: boolean; witnesses: { name: string; agree: boolean }[];
  first_diff_offset: number | null; changed: { from: string; to: string } | null; field: string | null;
}
export interface FailedRecord { raw_id: string; event_id: string | null; seq: number; batch_id: number; device: DeviceId | null;
  time: number | null; first_diff_offset: number | null; changed: { from: string; to: string } | null; field: string | null; }
export interface WitnessStatus { name: string; agree: boolean; mismatched_batches: number[]; }
export interface LedgerVerifyResult { verdict: 'verified' | 'tampered' | 'witness_mismatch'; checked_records: number; checked_batches: number;
  took_ms: number; failed_records: FailedRecord[]; failed_batches: { batch_id: number; reason: string }[]; witness_status: WitnessStatus[]; }
export interface LedgerBatch { batch_id: number; first_seq: number; last_seq: number; leaf_count: number; merkle_root: string;
  prev_head: string; head: string; signature: string; sealed_at: number; witnesses: { name: string; cosigned: boolean }[]; }
export interface WitnessInfo { name: string; label: string; pubkey_fingerprint: string; last_cosigned_batch: number; status: string; }
export interface SourceInfo { device: DeviceId; vendor: string; product: string; format: FormatId; parser: string; first_seen: number;
  last_seen: number; events_total: number; rate_epm: number; expected_gap_s: number | null; status: 'learning' | 'active' | 'silent'; silent_for_s: number; }
export interface QuarantineGroup { group_id: string; shape_signature: string; shape_label: string; reason: QuarantineReason; count: number;
  first_seen: number; last_seen: number; transport: string; peer_ip: string; sample_lines: string[]; }
export interface DraftTestResult { draft_id: string; promotable: boolean; holdout: { passed: number; total: number };
  all: { passed: number; total: number }; roundtrip: { passed: number; total: number; min_coverage: number };
  ocsf_valid: { passed: number; total: number }; failures: { index: number; check: string; detail: string }[];
  samples: { index: number; raw: string; ocsf: Record<string, unknown>; lineage: LineageEntry[] }[]; }
export interface IncidentSummary { incident_id: string; title: string; attacker_ip: string; target_ip: string | null; risk: number;
  level: 'Low' | 'Medium' | 'High'; stages: ('recon' | 'credential' | 'access')[]; devices: DeviceId[]; event_count: number;
  first_time: number; last_time: number; status: 'open' | 'closed'; }
export interface IncidentStage { stage: 'recon' | 'credential' | 'access'; label: string; first_time: number; last_time: number;
  devices: DeviceId[]; event_count: number; headline: string; event_ids: string[]; }
export interface Stats { raw_total: number; normalized_total: number; quarantined_total: number; formats_detected: number;
  parse_coverage_pct: number | null; ingest_rate_eps: number; sealed_records: number; sealed_batches: number; cosigned_batches: number;
  open_incidents: number; sources_total: number; sources_silent: number;
  last_bench: { eps: number; machine: string; measured_at: number } | null;
  clock: { now_ms: number; label: string; display_tz: string }; }
export interface SearchResult { question: string; engine: 'llm' | 'template'; model: string | null; sql: string; params: { now_ms: number };
  clock_caption: string; columns: string[]; rows: (string | number | null)[][]; row_count: number; took_ms: number; }
export interface DeliveryStatus { siem: { mode: 'file_sink'; target: string; forwarded: number; last_forwarded: number | null; last_payload: string | null; status: string };
  lake: { exports: { file: string; rows: number; bytes: number; created: number }[] }; retention: { available: boolean }; }
export interface ParquetExport { file: string; rows: number; duckdb_rows: number; bytes: number; took_ms: number; }
export interface TamperInfo { raw_id: string; offset: number; from: string; to: string; field: string; }

// ---- additions: response shapes from TRD.md §16 that §6.2 doesn't name -----------------------------------------
export type ComponentStatus = { status: string; detail?: string; ok_count?: number; total?: number; model?: string; checked_at?: number };
export interface Health { status: 'ok' | 'degraded'; demo_mode: boolean; version: string; components: Record<string, ComponentStatus>; }
export interface DemoState { demo_mode: boolean; phase?: DemoPhase; speed?: 10 | 20 | 40; silenced?: string[]; tampered?: boolean;
  resealed?: boolean; unknown_injected?: boolean; send_errors?: number; clock?: { now_ms: number; label: string }; reset?: boolean; }
export interface IncidentDetail extends IncidentSummary { stages_detail: IncidentStage[]; risk_breakdown: { stages: number; devices: number; ordered: number }; events: EventSummary[]; }
export interface ParserInfo { name: string; version: string; status: string; origin: 'builtin' | 'ai_draft' | 'user'; format: FormatId;
  approved_by: string | null; approved_at: number | null; roundtrip_pass_rate: number | null; events_parsed: number; }
export interface ParserDraft { draft_id: string; group_id: string; status: 'drafted' | 'tested' | 'approved' | 'rejected';
  origin: 'llm_live' | 'llm_cached' | 'hand_authored'; model: string | null; generated_at: number | null; yaml: string;
  train_count: number; holdout_count: number; holdout_indexes: number[]; test?: DraftTestResult | null; }
export interface RetentionReport { generated: number; statement: string; retention_target_days: number;
  sources: { device: DeviceId; oldest: number; newest: number; records: number; sealed: boolean }[];
  ledger: { verdict: LedgerVerifyResult['verdict'] | null; last_verified: number | null }; note: string; }
export interface EventQuarantined { raw_id: string; seq: number; time: number; group_id: string; reason: QuarantineReason; preview: string; }
export interface ApiErrorBody { error: { code: string; message: string; detail: Record<string, unknown> } }
