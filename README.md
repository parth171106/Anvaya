# ANVAYA — Every Perimeter Log, One Verifiable Truth

Smart India Hackathon 2026 · **SIH26156 Universal Log Pre-processing Framework** · NTRO · Blockchain & Cybersecurity · Software

ANVAYA ingests logs from perimeter devices (firewall, IDS, VPN, router) in any format and turns each one into a standard
OCSF record that can be proven faithful to the original:

- **Seal.** Every original byte is stored untouched, hashed (SHA-256) and sealed in Ed25519-signed Merkle batches that two
  witness stores co-sign.
- **Normalise.** YAML parser packs map each format to OCSF, with byte-level lineage for every field and a lossless
  round-trip proof.
- **Use.** Cross-device attack correlation, log-silence alerts, plain-English search (a local LLM writing guarded,
  read-only SQL, with a template fallback), AI-drafted parsers for unknown formats behind held-out tests and human
  approval, and Parquet export.

Everything runs offline in Docker. All demo traffic is **synthetic lab data** from a deterministic generator.

## Run it

Prerequisites: Docker with the Compose plugin; for local development also Python 3.11+ and Node.js LTS.

```bash
docker compose build
./demo.sh                      # stack up, reset, prints "ANVAYA ready · open http://localhost:8080/overview"
./demo.sh --speed 10           # the 3:50 main cut; --speed 40 for the 60 s cut; --no-llm to skip Ollama
```

Optional local model (pulled once, while online): `docker compose --profile llm up -d ollama && docker compose exec ollama ollama pull qwen2.5:3b`.
Without it, Search uses query templates and says so.

| Command | What it does |
|---|---|
| `make test` | Backend pytest (`cd backend && pytest -q`) and frontend lint + Vitest |
| `make e2e` | `./demo.sh --speed 40`, then the Playwright golden path (fails on any console error) |
| `make offline-test` | The full self-check inside `docker run --network none` |
| `make bench` | Measured throughput → `docs/BENCHMARKS.md` (see that file for Docker Desktop) |
| `make prebake` | Drafts the acme-edge parser with Ollama and caches it for the demo |
| `make dev-api` / `make dev-ui` | Uvicorn on :8000 with reload / Vite on :5173 (proxies `/api`) |

Presenter keys (demo mode): `` ` `` panel · `1` start · `2` unknown source · `3` silence fw01 · `4` tamper · `5` insider re-seal · `6` speed · `0 0` reset.

## Expected outcomes a–k

| # | Outcome (from the brief) | ANVAYA feature | Tier | Proof (command or test) |
|---|---|---|---|---|
| a | Preserve complete raw data without information loss | Append-only raw vault; SHA-256 per record; raw stored before parsing | REAL | `pytest backend/tests/test_vault.py::test_bytes_roundtrip` · `curl -s localhost:8000/api/raw/<raw_id> \| sha256sum` matches `raw_sha256` |
| b | Extract and parse source-specific attributes | Parser packs `cisco-asa`, `suricata-eve`, `fortigate-kv`; vendor fields kept in `unmapped` | REAL | `pytest backend/tests/test_parsers.py` (golden files per sample line) |
| c | Normalize fields into a common event taxonomy | OCSF mapping to classes 4001, 2004, 3002; validated against the vendored schema | REAL | `pytest backend/tests/test_ocsf_validation.py` |
| d | Maintain traceability between normalized and original events | `raw_id` + `raw_sha256` on every event; byte lineage per field; inclusion proof per record | REAL | `pytest backend/tests/test_roundtrip.py` · `curl -s -X POST localhost:8000/api/ledger/verify/<raw_id>` |
| e | Plug-and-play onboarding of new log sources | YAML packs hot-loaded; AI parser builder flow (draft → tests → approve → replay) | REAL (packs) · SIM (draft step) | SCN-04 in the video · `pytest backend/tests/test_parser_drafts.py` |
| f | Unified visibility across enterprise environments | One console and one schema across vendors; cross-device incident timeline | REAL | SCN-01 · `pytest backend/tests/test_correlation.py::test_scenario_yields_one_high_incident` |
| g | Efficient SIEM and data lake integration | Parquet export via DuckDB; SIEM forwarder writing RFC 5424/JSON payloads | REAL (Parquet) · SIM (SIEM target) | `curl -s -X POST localhost:8000/api/export/parquet` · first line of `/data/outbox/siem-forward.ndjson` |
| h | AI/ML-ready security and operational analytics | Typed, flattened OCSF columns in Parquet; NL search over normalized data | REAL | `duckdb -c "select count(*) from '/data/lake/*.parquet'"` |
| i | Reduced parser development effort | Declarative packs; AI-drafted parser gated by held-out tests and round-trip check | REAL (gates) · SIM (draft) | SCN-04: held-out 6/6, lossless 20/20 |
| j | Deployable in an air-gapped network | No runtime network calls; bundled fonts, model and schema; live network-route check | REAL | `make offline-test` (runs in `docker run --network none`) |
| k | Packaged in a container, platform independent | Docker Compose for `api`, `ui` and optional `ollama` | REAL | `docker compose up -d && curl -s localhost:8000/api/health` |

**What is simulated, and labelled so in the UI:** the AI draft step uses a cached draft (from an earlier local-LLM run,
or hand-authored), while the tests, approval and replay run live. The two witness nodes are local stores with their own
keys. SIEM delivery goes to a file sink. The retention report is a template filled from real counts, and says
"supports", never "certified".

## Repository

`backend/` FastAPI app (vault, ledger, parsers, OCSF, intel, search, AI parser builder, delivery) · `generator/`
deterministic scenario · `frontend/` React console · `bench/` load test · `docs/` architecture, benchmarks. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Roadmap

Kafka-compatible partitioned stream with stateless worker scale-out · PostgreSQL and object storage behind the existing
`Repository`/`RawStore` interfaces · witness services run by independent organisations over HTTPS · Wazuh/OpenSearch and
syslog/HTTP SIEM sinks · RBAC and Ed25519-signed parser packs · more formats (Palo Alto, pfSense, CEF/LEEF) · an offline
install bundle.
