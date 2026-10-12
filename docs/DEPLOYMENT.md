# Deploy ANVAYA on one cloud VM

This is a small college deployment with an owner and private user accounts. It keeps FastAPI, SQLite,
the raw vault and local witnesses on one persistent Linux VM. The Windows collector
runs on your Windows computer and forwards logs to the VM over authenticated HTTPS.
The cloud server cannot read your computer's Windows Security log by itself.

## Hosting choice and cost

For a new account used for a college semester, the recommended starting point is the
**AWS Free account plan** with one EC2 Linux VM. Eligible new customers receive $100
in credits and can earn more; the Free plan ends after six months or when its credits
are exhausted. Keep the account on the Free plan and export your data before it ends.
Check the account's actual eligibility, available services and credit balance before
launching the VM. See the [official AWS Free Tier FAQ](https://aws.amazon.com/free/free-tier-faqs/).
The application does not create cloud resources automatically. Provisioning and account
plan selection are separate from installing the application.

A VM fits the current architecture: ingestion, normalization and sealing run in one
long-lived process, and SQLite, log segments and signing keys need persistent storage.
Vercel Functions have a read-only filesystem apart from temporary scratch space and
execution limits; this full backend therefore needs a different architecture to run
there. See [Vercel's runtime documentation](https://vercel.com/docs/functions/runtimes).

Google Cloud's published Free Tier currently includes an eligible `e2-micro` in
`us-west1`, `us-central1` or `us-east1`, 30 GB-months of **standard persistent disk**,
and limited outbound transfer. It requires a billing account. Check eligibility,
external IP, disk type, domain and traffic costs before creating resources; this is
not a promise of a zero-cost public website. See the
[official Free Tier limits](https://docs.cloud.google.com/free/docs/free-cloud-features#compute).
The same deployment files can run on another Linux VM with Docker Compose.

Small free-tier VMs may not have enough memory to build the frontend. Build the images
on a larger development machine and transfer them if needed. The deployment disables
Ollama: built-in parsers and template search work without a model. Memory use and load
capacity still need measuring on the selected VM.

## What is included

- One owner plus private user accounts, PBKDF2-SHA256 password hashes, and per-account collector keys
  stored as a SHA-256 hash on the server. No default login or shared preset password.
- Random server-side sessions lasting eight hours, HttpOnly cookies, SameSite=Strict,
  Secure cookies on HTTPS, sign-out, and a global limit of ten login attempts per minute.
- Same-origin checks and a custom header for browser writes. Collector tokens cannot
  read events, download raw logs, export data, change parsers or access the event stream.
- Existing SSE and raw-log links are scoped to each user's workspace. Expired or
  revoked sessions stop receiving stream data. A server restart requires signing in again.
- Authenticated deployments disable the unauthenticated UDP listener. HTTPS ingestion
  is the supported remote path. Only ports 80 and 443 are published by the deployment stack.
- Caddy handles HTTPS; one Docker volume holds the database, vault, keys, receipts,
  witnesses and output files. Docker restarts the services after a reboot.

Authentication is opt-in for the existing localhost pilot. The deployment configuration
sets `ANVAYA_AUTH_REQUIRED=1` and refuses startup without valid credential files.
Do not publish the localhost pilot configuration on a public server.

## 1. Create credentials locally

From the ANVAYA folder in PowerShell, using the already installed backend dependencies:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m app.auth --directory secrets
```

Enter an administrator username and a password of at least 12 characters. The command
asks twice, does not print the password or API key, and refuses to overwrite existing
files. It creates:

- `secrets/auth.json`: password and key hashes; copy this to the VM in the same path.
- `secrets/collector.key`: the actual collector key; keep this on the Windows collector
  computer. Do not commit it, put it in a URL, or copy it into the frontend.

The secrets directory is excluded from Git and the backend Docker build context. Restrict
access to these files to your account (on Windows, check the folder's Security permissions).
There is no automatic password-reset flow. In the deployed multi-user mode, users
replace their collector key from Account and update their local key file. Password
recovery requires the operator to verify the request and update that account's salted
hash in the registry during maintenance. The auth file is only the initial bootstrap;
replacing it does not rotate credentials after migration. Existing sessions end when
the API restarts.

## 2. Prepare the Linux VM

Install Docker Engine and the Compose plugin using the
[official installation instructions](https://docs.docker.com/engine/install/).
Copy this repository's source and `secrets/auth.json` to the VM; exclude local `data/`,
`.venv/`, `node_modules/` and the collector key. Start with empty cloud storage.

Point a DNS hostname you control at the VM. Configure the VM firewall to allow TCP 80
and 443; restrict SSH to your own access. Do not expose API port 8000 or UDP 5514.
Caddy needs working DNS and reachable ports to obtain its certificate; see
[automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https).

On the VM, from the repository root:

```sh
cp .env.deploy.example .env.deploy
# Edit .env.deploy: ANVAYA_DOMAIN=your.actual.hostname (no scheme or path).
chmod 600 secrets/auth.json .env.deploy
docker compose --env-file .env.deploy -f docker-compose.deploy.yml config --quiet
docker compose --env-file .env.deploy -f docker-compose.deploy.yml up -d --build
docker compose --env-file .env.deploy -f docker-compose.deploy.yml ps
```

Open `https://your.actual.hostname/overview` and sign in. The default console is empty
until the Windows collector sends real logs. The cloud storage is separate from your
local pilot; deploying does not upload its historical logs automatically.

Run exactly **one API worker/replica**. Sessions, queue ownership and signing state use
the single-process design. Do not scale this Compose service horizontally.

## 3. Connect your Windows computer

Open Administrator PowerShell in the ANVAYA folder:

```powershell
.\.venv\Scripts\python.exe -m collectors.windows_auth `
  --api https://your.actual.hostname `
  --api-key-file .\secrets\collector.key `
  --checkpoint .\data\cloud-windows-auth-checkpoint.json
```

Use a separate checkpoint for each destination. The initial lookback is 15 minutes;
use `--lookback-minutes` on the first run if needed. Remote HTTP and missing API keys
are rejected. TLS verification stays enabled, redirects are not followed, and invalid
credentials stop collection. For a private CA, supply `--ca-file path\to\ca.pem`.

Temporary connection failures and HTTP 429/5xx retry with capped backoff. Stable event
keys prevent duplicate records on replay, including after a server restart. `--once`
imports one batch and exits; it still waits/retries during temporary API failures.

## 4. Check the deployment

1. `/api/ready` reports only `{"status":"ok"}` without authentication. `/api/events`
   returns 401 in a browser that has not signed in.
2. Sign in; inspect the real device name and incoming Authentication events.
3. Verify a record and the complete ledger from Integrity.
4. Sign out; refreshing a protected route returns the login screen.
5. Restart the API container. Sign in again and confirm logs are retained. Leave the
   collector running and check that it resumes with the same checkpoint.
6. Confirm the cloud firewall exposes only the intended HTTPS/HTTP and restricted SSH
   paths. Read container logs if startup fails; never paste credential files into logs.

## Backups and limits

For a consistent backup, stop the API before copying the **entire** `deploy-data` volume,
then start it again. The database, raw segments, signing keys and witness stores form one
set; restoring only SQLite is insufficient. Save a private copy of `secrets/auth.json`
separately. Restore into an empty volume and verify the ledger before reconnecting the
collector. Do not run `docker compose down -v` against valuable data.

There is no automatic backup/restore tool or scheduled retention policy in this phase.
Local witnesses are not independent external witnesses, and SIEM output remains a file.
This is a small deployment, not a multi-user or production security service.

## Validation status

Backend authentication, collector restrictions, restart/retry behavior and the local
browser login flow are tested. On 12 October 2026, the GitHub revision was built and
started on an Ubuntu 24.04 EC2 VM with Docker Compose. Public HTTPS certificate validation,
readiness, administrator login/logout, anonymous request rejection and collector access
restrictions passed. This verifies a running small deployment, not a load-capacity claim.
The initial cloud database is empty; real collection requires running the Windows collector.

For the prepared Windows checkout, `collect-cloud.ps1` uses the saved hostname in
`data/cloud-endpoint.txt`, the private `secrets/collector.key`, and a separate cloud
checkpoint. Run it from Administrator PowerShell. On another checkout, provide
`-Api https://your-hostname` explicitly. Do not reuse the cloud checkpoint for a different server.

The CSRF approach follows the
[OWASP guidance on custom request headers and same-origin checks](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Public signup and private workspaces

The deployment profile enables `ANVAYA_MULTI_USER=1` and `ANVAYA_PUBLIC_SIGNUP=1`.
Share `/join`: people choose a username and password, explicitly accept the Terms
and acknowledge the Privacy Notice, then receive a private workspace. Signup uses
usernames; email verification and automatic password recovery are not implemented.
The default capacity is ten accounts in total, including the owner and disabled
accounts. Signup is globally throttled to five attempts per minute and login to ten.
This is a bounded college pilot, not a large public hosting service.

The owner's existing username, password hash, collector-key hash and data directory
are preserved during the first upgrade. Account credentials are then stored in
`/data/accounts.db`; editing the bootstrap `auth.json` does not rotate existing
credentials afterward. Sessions expire on restart. The owner must acknowledge the
terms on their next console login; their existing collector continues to work.

Other users get server-generated workspace IDs and separate SQLite databases,
vaults, signing keys, witness stores, parser packs, event buses, exports and workers
under `/data/workspaces/<id>`. Request parameters cannot select another workspace.
The owner can list usernames, issue/revoke optional invitations and disable accounts,
but the console does not grant the owner cross-workspace log browsing. The server
operator still has infrastructure-level access: this is not end-to-end encryption.
Run one API worker; account enrollment and SQLite operations are coordinated in that
one process. Do not add multiple API replicas without redesigning this model.

From **Account**, each user downloads the collector ZIP and generates/downloads
`collector.key`. The ZIP contains only source and server URL, not credentials or
logs. Key replacement invalidates the previous key immediately. Each computer and
account needs its own extracted collector folder/checkpoint. Windows collection
requires Administrator PowerShell and begins with the previous 15 minutes of 4624/
4625 events. Only collect data that the user is authorized to share.

Limits: 100 MiB or 50,000 raw records per workspace; 500 records per request; 256 KiB
per record; five stored Parquet exports. These bound application use but are not a
complete disk quota: normalized data, audit records, indexes and logs also use disk.
Monitor VM disk space. Disabling an account revokes sessions and collector access,
but retains its data and does not free an account slot automatically.

## Terms, privacy and operator responsibilities

Public pages `/terms` and `/privacy` are available before signup. They are backed by
`backend/app/api/routes_legal.py`; `TERMS_VERSION` in `backend/app/accounts.py` controls
which version is acknowledged. Bump it after material changes and retain the older
text in your release archive. Acceptance records store account ID, version and UTC
time. A checkbox and record of acceptance are evidence, not a guarantee that every
clause is enforceable.

Operator: **ANVAYA project team**. Support/privacy: **anvaya-sih@proton.me**. Override
these with `ANVAYA_OPERATOR_NAME` and `ANVAYA_SUPPORT_CONTACT` in `.env.deploy` as
needed. Keep the contact monitored. These plain-language draft terms explain the
educational scope, authorized use, possible errors/outages, warranty limitations and
non-excludable rights. They do not confer immunity from complaints or liability.
Have a qualified lawyer review them before relying on them as legal protection.
References: [Indian Contract Act](https://www.indiacode.nic.in/handle/123456789/2187)
and [MeitY data protection framework](https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025686cadad39.pdf).

There is no automatic time-based deletion. Respond to privacy/access/deletion
requests through the support contact. Verify the requester's authority without
asking for their password or collector key. For an approved deletion, stop the API,
identify the account's exact server-generated workspace directory, remove that
account's raw data, database, keys, witness copies, packs, outbox and exports, and
remove its registry/acceptance records and any associated invitations. Account
`owner` uses the original root data directory and requires special care: never
recursively remove `/data`, because it contains other users and the account registry.
Remove relevant backups separately, or explain any required retention to the user.
Restart the API and verify that both login and collector access fail. Deletion must
be explicitly authorized and checked by the operator; the application does not
currently provide an automated deletion or password-reset workflow.

To roll back this upgrade, retain a private, consistent snapshot of the Docker data
volume taken with the API stopped, plus the previous API/UI images. Never put a
snapshot, account database, logs, passwords or collector keys on GitHub.
