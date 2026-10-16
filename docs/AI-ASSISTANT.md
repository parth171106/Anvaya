# Optional Gemini assistant

ANVAYA supports natural-language search, follow-up filters, result explanations,
incident explanations and suggested investigation steps. Built-in search remains
available without a provider key. AI is off by default.

## Private configuration

For local development, save only the API key in `secrets/gemini-api.key`.
The `secrets/` directory and `*.key` are ignored by Git and excluded from Docker
builds. Never paste the key into a command, browser field, issue, chat or frontend
environment variable. Restrict file permissions to the operator/service account.

Set backend environment variables (key file must be an absolute path):

```text
ANVAYA_AI_ENABLED=1
ANVAYA_AI_MODEL=gemini-3.5-flash-lite
ANVAYA_AI_KEY_FILE=/absolute/private/path/gemini-api.key
ANVAYA_AI_EVIDENCE_ENABLED=1
```

On the deployment VM, put the key in `secrets/ai/gemini-api.key`, set directory
mode 700 and file mode 600. Compose mounts only this AI directory read-only into
the API container; the UI never receives the key. Set the enabled/model/evidence
flags in `.env.deploy`, then rebuild/recreate the API and UI. Setting both enabled
flags back to 0 disables hosted assistance without removing stored logs.

Gemini 3.5 Flash-Lite passed a synthetic integration test on 2026-10-14. Gemini
3.8 Flash was listed as available but returned temporary high-demand errors.
Model availability and quotas depend on the provider project. There is no silent
switch to a different provider or model. Check [models](https://ai.google.dev/gemini-api/docs/models)
and [pricing/data-use differences](https://ai.google.dev/gemini-api/docs/pricing)
before enabling it. This integration does not enable billing or purchase a plan.
Use only synthetic/non-sensitive data with free-tier processing; arrange suitable
paid processing before sending sensitive logs. An API key alone does not establish
that a paid plan or particular data-retention policy is in effect.

## User flow

1. In Search, select the Gemini sharing checkbox and ask, for example,
   “Show failed SSH logins from yesterday.” Review the generated SQL and dates.
   Questions such as “show me any intrusion” or “Show detected incidents” search
   the current workspace's detected incidents locally and return links to their
   evidence. This does not establish a confirmed intrusion. Optional incident filters
   include an IPv4 address, today/yesterday, a rolling window, risk level and status.
   Unsupported filters produce an explicit message instead of silently dropping them.
2. Select “Follow up on …” and ask “Only show those from 192.0.2.10.” Uncheck
   follow-up to start a fresh question. Context expires after ten minutes.
3. For a non-empty result, choose “Preview data to be shared”, review the sample,
   check the consent box and choose “Explain and suggest next steps”.
4. Incident details offer the same preview/consent flow. Links point to the
   incident's stored events; search citations point to rows in the displayed table.

The generator receives the question, fixed schema, time boundaries and previous
question/SQL when requested. It does not receive query results. Natural-language
questions and SQL literals can themselves contain identifying information.
Explanations send only the previewed snapshot: up to 30 search rows or 20 incident
events plus context (including per-stage counts for incidents), bounded to approximately 18 KB of JSON, with text fields capped
at 256 characters. No automatic raw-log, password, recovery-code, collector-key or
parser-draft integration is connected to this hosted client. Normalized text may
still contain sensitive material: review it before sharing.

## Boundaries and limitations

- Context and previews are scoped to the authenticated account's container and
  expire after ten minutes (up to twenty each). Restarting clears them.
- Generated SQL passes an AST allow-list and executes on a read-only SQLite
  connection, with a two-second execution limit and at most 200 returned rows.
  Hosted queries also reject joins, nested SELECTs, CTEs and unknown columns.
- Every explanation claim must cite a supplied row. The provider receives a JSON
  schema restricted to the previewed citation IDs, and the server validates the
  response again. Up to 30 citations per claim are allowed to cover a full sample.
  Incident samples include each available attack stage within the 20-event budget. Reference validation does not
  prove that the model interpreted that row correctly. Outputs are displayed as
  text, never executed or rendered as HTML. Suggestions do not modify systems.
- AI does not determine cryptographic integrity, change incident scores or verify
  a breach. Use the existing event/ledger integrity checks separately.
- Per workspace: one in-flight call, ten attempts/minute and 100 attempts/day UTC.
  Daily counts persist across restarts; failed calls count too. These are application
  limits, not a provider spending guarantee. Configure provider budgets/quotas too.
- The deployment uses one API worker. Do not scale workers without moving context
  and rate-limit coordination to a shared store.
- Provider errors return a bounded generic message; prompts, provider response
  bodies and keys are not logged. Built-in search is explicitly selectable after
  failures; a failed follow-up is never silently treated as an unrelated search.
- Updated privacy notice version: 2026-10-14. Existing users must acknowledge it
  themselves before using the updated console.

## Validation

Offline tests exercise consent, account isolation, context expiry, SQL rejection,
provider-error redaction, limits and citations. The separate real-provider lab uses
only generated SSH records from reserved example IP addresses; it is not evidence
of a real attack. No real user records are needed to validate the integration.
# Parser drafting and quarantined formats

Gemini search and evidence explanations are separate from parser drafting. Parser drafting never automatically sends raw quarantine samples to Gemini.

In live mode, the known 12-field `EDGE` session format can use the bundled hand-authored Acme Edge template. The draft is labelled **hand-authored**, has no AI model or generation timestamp, and still requires **Run tests → Approve & replay**. This is an existing format mapping, not general-purpose AI inference. Similar delimiters alone do not qualify another format for this template.

Other formats require the configured local Ollama model. If it is unavailable, the UI explains that dependency and the original records stay sealed in quarantine. Draft approval requires all four gates to pass, including successful conversion of declared IP and integer fields. Approved hand-authored templates are recorded as user parsers rather than AI drafts.

