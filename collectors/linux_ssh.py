"""Forward OpenSSH authentication results from systemd's journal to ANVAYA.

Accepted/Failed and Invalid user messages are selected. Service lifecycle messages, PAM session
messages and disconnects are excluded to retain authentication evidence without session lifecycle noise.
The raw message is retained; journal metadata supplies the ISO UTC timestamp,
hostname and PID. The durable journal cursor advances only after acknowledgement.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from collectors.windows_auth import local_api, request_with_retry, save_checkpoint

AUTH_MESSAGE = re.compile(r"^(Accepted|Failed|Invalid user) ")


def journal_line(entry: dict) -> str | None:
    message = entry.get("MESSAGE")
    # Non-text journal values must not be silently acknowledged and discarded.
    if not isinstance(message, str):
        raise ValueError("Journal MESSAGE is not text; cursor left unchanged")
    if not AUTH_MESSAGE.match(message):
        return None
    process = entry.get("SYSLOG_IDENTIFIER") or entry.get("_COMM")
    if process not in ("sshd", "sshd-session"):
        return None
    host, pid = entry.get("_HOSTNAME"), entry.get("SYSLOG_PID") or entry.get("_PID")
    if not isinstance(host, str) or not host or any(c.isspace() for c in host) or not str(pid).isdigit():
        raise ValueError("Missing or invalid journal hostname/PID")
    micros = int(entry["__REALTIME_TIMESTAMP"])
    timestamp = datetime.fromtimestamp(micros // 1_000_000, timezone.utc).isoformat(timespec="seconds")
    return f"{timestamp} {host} {process}[{pid}]: {message}"


def deliver(client, entry: dict, state: dict, checkpoint: Path) -> bool:
    cursor = entry.get("__CURSOR")
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("Journal entry lacks a cursor")
    line = journal_line(entry)
    if line is not None:
        identity = state["machine_id"] + "\n" + cursor
        key = "linux-ssh-v1:" + hashlib.sha256(identity.encode()).hexdigest()
        response = request_with_retry(client, "POST", "/api/ingest", json={"lines": [line]},
                                      headers={"Idempotency-Key": key, "X-Anvaya-Require-Live": "true"})
        if response.headers.get("Idempotency-Key") != key or response.json().get("accepted") != 1:
            raise RuntimeError("API did not acknowledge durable receipt; cursor left unchanged")
    updated = {**state, "cursor": cursor,
               "sent": state.get("sent", 0) + int(line is not None),
               "skipped": state.get("skipped", 0) + int(line is None)}
    save_checkpoint(checkpoint, updated)
    state.update(updated)
    return line is not None


def journal_command(state: dict, once: bool) -> list[str]:
    command = ["journalctl", "--unit=ssh.service", "--unit=sshd.service", "--output=json", "--all", "--no-pager"]
    command += ["--after-cursor=" + state["cursor"]] if state.get("cursor") else ["--since=" + state["since"]]
    if not once:
        command += ["--follow", "--no-tail"]
    return command


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", type=local_api, required=True)
    ap.add_argument("--api-key-file", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, default=Path("/var/lib/anvaya-ssh/checkpoint.json"))
    ap.add_argument("--lookback-hours", type=int, default=24)
    ap.add_argument("--once", action="store_true", help="Drain available journal entries then exit")
    args = ap.parse_args(argv)
    if sys.platform != "linux":
        ap.error("Run this collector on the Linux SSH server")
    if args.lookback_hours < 0:
        ap.error("lookback must be nonnegative")
    os.umask(0o077)
    try:
        # One process per checkpoint; prevents cursor rollback by concurrent collectors.
        import fcntl
        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        lock = args.checkpoint.with_suffix(".lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        key = args.api_key_file.read_text().strip()
        if len(key) < 32 or not key.isascii() or any(c.isspace() for c in key):
            raise ValueError("Invalid collector key file")
        machine = Path("/etc/machine-id").read_text().strip()
        identity = {"machine_id": machine, "api": args.api,
                    "key_id": hashlib.sha256(key.encode()).hexdigest()}
        if args.checkpoint.exists():
            state = json.loads(args.checkpoint.read_text())
            if any(state.get(k) != v for k, v in identity.items()):
                raise ValueError("Checkpoint belongs to another machine, destination or key; use a new checkpoint")
        else:
            state = {**identity, "since": (datetime.now(timezone.utc) - timedelta(hours=args.lookback_hours)).isoformat()}
            save_checkpoint(args.checkpoint, state)
        with httpx.Client(base_url=args.api, headers={"Authorization": f"Bearer {key}"}, timeout=30,
                          trust_env=False, follow_redirects=False) as client:
            request_with_retry(client, "GET", "/api/health")
            # stderr is inherited so permission/cursor errors are visible in systemd.
            process = subprocess.Popen(journal_command(state, args.once), stdout=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="strict")
            try:
                for raw in process.stdout:
                    if deliver(client, json.loads(raw), state, args.checkpoint):
                        print(f"SSH authentication record delivered; total={state['sent']}", flush=True)
                if process.wait() != 0:
                    raise RuntimeError("journalctl failed; inspect service logs; checkpoint retained")
                if not args.once:
                    raise RuntimeError("journalctl follow ended unexpectedly")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
        print(f"Finished: sent={state.get('sent', 0)}, skipped={state.get('skipped', 0)}", flush=True)
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, httpx.HTTPError) as exc:
        # HTTP exception strings can include response bodies; report type without credentials/log contents.
        print(f"SSH collector stopped: {type(exc).__name__}: " + (str(exc) if not isinstance(exc, httpx.HTTPError) else "HTTP request failed"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
