# Linux SSH collection

The OpenSSH parser accepts `journalctl -o short-iso` authentication records. The
Linux collector reads the journal's JSON output and renders each selected record
as ISO UTC time, hostname, process/PID and the unchanged MESSAGE. Journal timestamps
are rendered to seconds, matching short-iso; the cursor provides event identity.

Supported results: `Accepted` and `Failed` publickey/password/keyboard-interactive
logins, including invalid users and IPv6 addresses. These map to OCSF Authentication
(3002), with raw evidence, source field locations and round-trip verification.
Service restarts, PAM session messages and disconnects are deliberately excluded;
they are not additional login attempts. Unknown Accepted/Failed message formats
are sent unchanged and quarantined by the parser rather than discarded.

## Installation on Ubuntu

Deploy the backend containing `openssh-journal.yaml` before starting the collector.
From a checkout on the server, install the collector and its service:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv
sudo useradd --system --user-group --home-dir /var/lib/anvaya-ssh --shell /usr/sbin/nologin anvaya-ssh
sudo install -d -m 755 /opt/anvaya-ssh
sudo cp -r collectors /opt/anvaya-ssh/
sudo python3 -m venv /opt/anvaya-ssh/venv
sudo /opt/anvaya-ssh/venv/bin/pip install httpx==0.28.1
sudo install -d -m 750 -o root -g anvaya-ssh /etc/anvaya-ssh
```

Save your account's collector key to `/etc/anvaya-ssh/collector.key`, owned by
`root:anvaya-ssh`, mode `0640`. Do not put a key in shell arguments or Git.
Create `/etc/anvaya-ssh/collector.env` containing your deployment's HTTPS origin:

```text
ANVAYA_API=https://your-hostname
```

```bash
sudo install -m 644 deploy/anvaya-ssh.service /etc/systemd/system/anvaya-ssh.service
sudo systemctl daemon-reload
sudo systemctl enable --now anvaya-ssh
sudo systemctl status anvaya-ssh --no-pager
sudo journalctl -u anvaya-ssh -n 20 --no-pager
```

The service reads the previous 24 hours on its first run, then follows new events.
The dedicated user has read access to the system journal. Its HTTP key grants
ingestion into one account, not dashboard access. HTTPS certificate validation
remains enabled. No SSH password authentication or firewall changes are needed.

The checkpoint lives at `/var/lib/anvaya-ssh/checkpoint.json`. It advances only
after server acknowledgement (or after an explicitly excluded lifecycle record).
Retries use the journal cursor and machine ID for durable duplicate prevention.
On restarts it resumes after the saved cursor, not from the most recent ten events.
If the source journal was vacuumed, historical records already removed from the
journal cannot be recovered. Watch the service's errors and keep journal retention
longer than expected outages. Use a separate checkpoint for a changed destination
or rotated key; overlapping records remain duplicate-safe within the same workspace.

## Checking the result

Sign into the destination account and open Live feed or Sources & parsers. Filter
by the server's actual hostname, not the `synthetic-lab-*` devices. A normal SSH
login should produce a Success authentication event with its source IP and raw log.
An ordinary successful login is not an incident. The existing cross-device rule
is unchanged; a dedicated SSH failures-followed-by-success rule is not implemented
by this collector. Do not label unrelated successful logins as compromises.

Run `sudo systemctl stop anvaya-ssh` to pause collection. This does not delete logs.
The collector does not configure Caddy access logging; that is a separate source.

Journal options: https://www.freedesktop.org/software/systemd/man/255/journalctl.html
