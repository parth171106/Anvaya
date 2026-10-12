# Deploy ANVAYA on one cloud VM

This is a small, single-administrator college deployment. It keeps FastAPI, SQLite,
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
No AWS account, VM or paid resource has been created by this project setup.

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

- One administrator account, PBKDF2-SHA256 password hashes, and a private collector key
  stored as a SHA-256 hash on the server. No default login or shared preset password.
- Random server-side sessions lasting eight hours, HttpOnly cookies, SameSite=Strict,
  Secure cookies on HTTPS, sign-out, and a global limit of ten login attempts per minute.
- Same-origin checks and a custom header for browser writes. Collector tokens cannot
  read events, download raw logs, export data, change parsers or access the event stream.
- Existing SSE and raw-log links work through the administrator session. Expired or
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
There is no web password-reset flow. To rotate credentials, create files in a new private
directory, replace the VM's auth file, recreate the API container, and update the collector
key file. Existing sessions end when the API restarts.

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
browser login flow are tested. Container builds, certificate issuance, VM sizing and
cloud networking must still be checked on a Docker-enabled machine and the chosen host.
Docker was unavailable on the development machine during this phase; no cloud resources
were created and no real logs were uploaded to a third party.

The CSRF approach follows the
[OWASP guidance on custom request headers and same-origin checks](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
