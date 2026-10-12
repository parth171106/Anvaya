# Live-log pilot

This pilot receives actual logs on localhost. It never starts the scenario generator.
For an authenticated HTTPS cloud server, use the separate [deployment guide](DEPLOYMENT.md).
The first collector supports Windows Security sign-in events: **4624 (success)** and
**4625 (failure)**. Existing Cisco ASA, FortiGate and Suricata parser packs remain available;
only their supported message/header variants normalize. Other formats are preserved in quarantine.

## Run on this Windows computer

From the repository root, prepare dependencies once (Python 3.11+ and Node 22.22+):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock pytest pytest-asyncio ruff
Push-Location frontend
npm.cmd ci
npm.cmd run build
Pop-Location
```

Start the service and built console together:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\pilot.ps1 Start
```

Open **http://127.0.0.1:8081/overview**. HTTP ingestion uses the same origin;
UDP listens on **127.0.0.1:5515**. The server runs in the background. It only binds
to loopback, because this pilot does not yet have user authentication or TLS.

```powershell
.\pilot.ps1 Status
.\pilot.ps1 Stop
```

The API, vault, SQLite database, keys and local witnesses use **data/live/**.
Starting or stopping never resets records. A database mode marker prevents opening demo
storage in live mode (or live storage in demo mode). Legacy nonempty storage without a
mode marker must be kept separate as well. Native demo and container demo data are untouched.

## Collect real Windows sign-ins

Open PowerShell **as administrator**, change to this repository, and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\pilot.ps1 Collect
```

Or import one batch of up to 200 existing events and exit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\pilot.ps1 Collect -Once
```

The account must have permission to read the Security log. The collector reports an error
and stops if Windows denies access. It does not modify Windows audit settings, create fake
sign-ins, or collect passwords. If auditing is disabled or no matching events exist, it
waits for genuine sign-in records; an empty dashboard is expected.

On first start it looks back **15 minutes**, then polls every five seconds. It saves
`data/live/windows-auth-checkpoint.json` after each acknowledged event and resumes from it.
If the API is offline, times out, or returns HTTP 429/5xx, the collector retries after
1, 2, 4, 8, 16, then 30 seconds (30 seconds maximum between retries). This also applies
to `-Once`; press Ctrl+C to stop waiting. Access errors, invalid events and permanent
HTTP errors stop collection with an explanation instead of retrying forever.
To use a different initial lookback, run the collector directly before its first run:

```powershell
.\.venv\Scripts\python.exe -m collectors.windows_auth --lookback-minutes 60
```

Only event IDs 4624 and 4625 from Microsoft-Windows-Security-Auditing are accepted by this
collector. It forwards the full XML returned by Windows `ToXml()` inside a JSON envelope,
plus fields derived from that XML. The vault hashes the exact received JSON bytes. This
preserves exported event XML; it is **not a byte-for-byte backup of the original EVTX file**.
Absent source IPs are left absent, and device names come from each event.

Check **Sources & parsers** for the actual computer name and **Live Feed** for Authentication
events. Open an event to inspect the raw envelope, original XML, OCSF fields and lineage.
After the five-second sealing window, use **Integrity → Verify ledger**.

## Ingest another source

Send UTF-8 newline-delimited logs with `Content-Type: text/plain`, or JSON shaped as
`{"lines": ["first raw log", "second raw log"]}`, to `http://127.0.0.1:8081/api/ingest`.
Text-line CR/LF separators are transport framing and are not part of the stored record.
The API returns accepted raw IDs; acceptance does not imply successful normalization.
Check quarantine for unsupported formats. Do not expose this unauthenticated pilot API
to your LAN or internet; use a local forwarder until access controls are implemented.

For retry-safe HTTP delivery, send **one log per request** with an `Idempotency-Key`
header (1–128 letters, digits, `.`, `_`, `:`, or `-`). Reusing the same key and bytes
returns the original raw ID with HTTP 202; reusing a key with different bytes returns
HTTP 409. `accepted: 1` acknowledges the record, including an already accepted record.
Requests without keys keep the original behavior. The Windows collector automatically
derives its key from the exact JSON envelope and checks that the API acknowledges it.

Optional Ollama at `http://127.0.0.1:11434` with `qwen2.5:3b` enables live parser drafting
and natural-language SQL. Without it, ingestion and the built-in parsers still work,
search uses supported query templates, and drafting reports unavailability. Live mode
never substitutes the demo's cached hand-authored draft.

## Optional Docker alternative

Use this standalone file rather than merging it with the demo configuration:

```powershell
docker compose -f docker-compose.live.yml up -d --build
```

It uses project `anvaya-live` and its own `live-data` volume. Console: localhost:8081;
direct API: localhost:8001; UDP: localhost:5515. Run either the native pilot or Docker,
since their published ports overlap. The Windows collector can use the console's API
proxy on port 8081. The Ollama host alias in this file targets Docker Desktop.

## Reliability and current boundaries

- Live ingestion fsyncs the vault before committing raw metadata with SQLite FULL
  synchronization. Accepted records still pending normalization are requeued on restart.
- The collector retries temporary API failures and sends each event with a stable key.
  SQLite commits that key and the raw record metadata in one transaction. Repeating
  the same keyed event after a lost reply or checkpoint does not add another record,
  including after a server restart. This applies to records sent by the updated
  collector; previously collected records are not retroactively deduplicated.
  The collector still needs its PowerShell window and does not run as a Windows service.
- If the Windows event log is cleared and record IDs move backwards, collection stops
  for investigation instead of silently moving its checkpoint. Events overwritten by
  Windows before collection cannot be recovered by this pilot.
- UDP has no delivery acknowledgement. Use HTTP for the Windows collector.
- Witnesses and their keys are still local. SIEM output is still a local file sink;
  its delivery counters are per process and it has no durable retry queue.
- The retention report describes current records and a target; it does not enforce a
  retention policy. Incident detection uses the existing limited correlation rules.
- A single-process queue and SQLite remain appropriate only for a measured, small pilot.
  Disk exhaustion, power-loss recovery, large loads and independent witness deployment
  require further work. The repository's old benchmark is hidden in live mode.

## Validation

### Simple college demonstration

After updating the code, restart the API with `pilot.ps1 Stop` then `pilot.ps1 Start`.
Stop any old collector with Ctrl+C, then relaunch `pilot.ps1 Collect` in its administrator
PowerShell window. Keep the existing checkpoint so collection resumes from the same place.

1. Show real Authentication events and the actual computer name in the live console.
2. Open one event and show its original Windows XML, normalized fields and integrity check.
3. In a second PowerShell window, run `pilot.ps1 Stop`. The updated collector waits/retries
   when it next has an event to send. Run `pilot.ps1 Start`; collection resumes automatically.
4. Use the automated recovery test below to demonstrate the lost-reply case: it accepts
   an event, discards the reply, reopens the server's storage and retries, then checks that
   exactly one record exists and its integrity verification passes.

```powershell
.\.venv\Scripts\python.exe -m pytest -q backend\tests\test_collector_recovery.py --basetemp data\test-recovery-manual
```

The project demonstrates collection, parsing, evidence preservation and integrity checks
on one computer. Local witnesses and a local SIEM output file are suitable demonstration
components; they are not independent external services.

### Regression checks

Tests use explicit fixtures in temporary directories, never synthetic records in the
live vault. From the repository root:

```powershell
New-Item -ItemType Directory -Path data -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest -q backend\tests --basetemp data\test-manual
.\.venv\Scripts\python.exe -m ruff check --config backend\pyproject.toml backend collectors
Push-Location frontend
npm.cmd run lint
npm.cmd test
npm.cmd run build
Pop-Location
```

`--basetemp` is disposable test storage; never point it at `data/live` or any valuable directory.
`test_live_pilot.py` covers actual normalization and schema validation, Unicode byte
lineage, XML preservation, checkpoint acknowledgement behavior, restart recovery,
demo isolation, API ingestion, verification, and SPA/API route separation.
`test_collector_recovery.py` covers temporary outages, capped retries, lost replies,
duplicate prevention across storage restarts, conflicting keys, atomic receipt persistence,
checkpoint write failures and compatibility with existing pilot databases.
