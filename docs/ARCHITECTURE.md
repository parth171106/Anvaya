# ANVAYA architecture

One Python process (FastAPI + Uvicorn) does the work, a React console shows it, and an optional local LLM
(Ollama, `qwen2.5:3b`) helps with search. Everything runs on one laptop, offline, under Docker Compose
(`api` :8000 and 5514/udp, `ui` :8080, optional `ollama`).

## Data path

```
fw01 · ids01 · vpn01 ──UDP 5514──┐
br01 ───────────────POST /api/ingest─┤
                                     ▼
  L1  vet (flags only) → raw vault (append-only segments, [u32 len][bytes], SHA-256) → raw_events
        └─ ledger sealer: 16 records → RFC 6962 Merkle root → head = SHA256("ANVAYA-HEAD-v1"‖id‖root‖prev)
           → Ed25519 signature → co-signed by witness-ntro and witness-certin (own keys, own stores)
  L2  queue → fingerprint (pack detect rules, by priority) → parse (regex | span-aware JSON | kv | delimited)
        → OCSF 1.9.0 map + validate → byte lineage + round-trip check → confidence → events
        └─ no pack / no rule / invalid → quarantine (grouped by shape) → AI draft → 4 gates → approve → replay
  L3  correlation (per external IP, 10-min windows, ≥ 2 stages) · silence monitor (real-time gaps)
      · NL search (Ollama → sqlglot allow-list → read-only SQLite; template fallback) · Parquet (DuckDB)
      · SIEM file sink (RFC 5424 + JSON) · retention report
  SSE /api/stream (ids, 2,000-message replay buffer) → console
```

Every stored event keeps `raw_id` and `raw_sha256`. Its `anvaya.lineage` gives the byte spans of every OCSF field,
and `unmapped` holds every extracted value with no OCSF home, so nothing is dropped. Verification re-reads every byte
from disk, rebuilds each root and head, checks each signature, and compares every head with each witness's own store.
A one-byte edit is named down to the record, byte offset and field. A re-signed ledger is caught by witness disagreement.

## Determinism

In demo mode a scenario clock starts at 10:00:00 IST, runs at 10/20/40× until 10:12:00 and then at 1×. The generator
derives every value from a line index (no randomness), and sealing is count-triggered during the scripted phase, so
batch numbers, the incident (`inc-0001`, risk 95) and the search results are the same on every take.

## Interfaces that carry the scale-out path

| Interface | MVP implementation | Production implementation |
|---|---|---|
| `RawStore` | Local segment files | Object store (MinIO/S3) with object lock; index in PostgreSQL |
| `Repository` | SQLite (WAL); `mode=ro` connection for search | PostgreSQL, `events` partitioned by day, `ocsf JSONB`, read-only role |
| `EventQueue` | In-process `asyncio.Queue`, one worker | Kafka-compatible topic partitioned by device; stateless workers |
| `WitnessClient` | Two in-process stores with separate keys | Witness services at independent organisations over HTTPS |
| `DraftSource` | Cached draft (demo) / live Ollama | Live drafting |
| `SiemSink` | File sink | Syslog / HTTP sinks (Wazuh, OpenSearch, Splunk-compatible) |
| `Clock` | Scenario clock (demo) / wall clock | Wall clock |

| MVP element | Production element |
|---|---|
| `raw_events` + segments | Immutable objects per segment; same framing |
| Flat `events` columns | The same `flatten()` feeds a Parquet lake partitioned `date=/hour=/device=` |
| `ledger_batches`, `witness_signatures` | PostgreSQL, one ledger per stream partition, heads published to witnesses |
| `quarantine`, `parsers`, `parser_drafts` | PostgreSQL; packs as Ed25519-signed files in a git-backed repository |
| `audit_log` (append-only triggers) | PostgreSQL with INSERT-only grants, mirrored to the vault |

## Deliberate MVP deviations

The MVP uses one in-process queue and worker, not a partitioned stream: a single-machine video gains nothing from a
fleet. It uses SQLite and local files, not PostgreSQL and MinIO: zero setup, offline. The AI draft in the video comes
from a cache, because live CPU latency is unpredictable on camera; the gates, approval and replay are live. The
witnesses are local, because independent operators can't be shown on one laptop.

## Measured

See [BENCHMARKS.md](BENCHMARKS.md): numbers are measured on a named machine and never estimated.
