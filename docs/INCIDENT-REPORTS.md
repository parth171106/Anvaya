# Incident PDF reports

Open an incident, save any investigation edits, then choose **Download PDF report**.
The checked **Verify included raw records now** option performs fresh record
checks. Uncheck it to export without verification. Downloaded PDFs contain account
evidence and notes; share only with intended recipients.

The authenticated, CSRF-protected `POST /api/incidents/{id}/report` accepts
`{"verify": true}` (default true) and returns an attachment with `Cache-Control:
no-store`. It uses the signed-in workspace, including when incident IDs are the
same in different accounts. Collector credentials cannot export reports.

Reports include the summary, rule explanation, stage timeline, investigation
state, controlled-test/demo/synthetic-source labels, latest 100 activity entries,
and earliest 200 linked events ordered by event time and ingestion sequence. Counts
disclose missing/omitted events and older activity. Each included event has its
event ID, raw ID, batch ID, fields, and fresh integrity outcome. Checked records
also include stored/current SHA-256 values. Times are UTC. Unsupported font glyphs
are printed as Unicode code points instead of disappearing. Raw payloads and AI
explanations are not embedded. No evidence is sent to an AI provider.

Record verification reuses the ledger's SHA-256, Merkle inclusion, Ed25519 signed
batch-head, and configured witness-head checks. Any failed check yields **FAILED**.
Unsealed, unavailable, skipped, or omitted evidence makes the overall outcome
**NOT CHECKED** unless a check failed. **VERIFIED** requires complete coverage of
the linked evidence and all included record checks passing. Empty incidents are
never marked verified. Per-record results remain visible when coverage is partial.

These checks do not verify normalized field accuracy, full historical chain
continuity, source truthfulness, or whether compromise occurred. Witness stores
are local, not independent external witnesses. The PDF is not digitally signed.
The export does not seal records, update stored verification metadata, mutate
investigation notes, or persist PDFs on the server. PDF layout runs off the API
event loop after taking the bounded incident snapshot. No schema migration is
required. ReportLab and its image/text dependencies are pinned in the backend lock
file; pypdf is used for tests only.

Validation covers real fixture proof success and byte tampering, unavailable and
unsealed proofs, explicit verification opt-out, coverage limits, long notes and
escaped markup, authentication/CSRF, collector denial, and cross-account isolation.
The sample in `output/pdf/` is generated from local synthetic test data; that folder
and PDF preview files are ignored by Git.
