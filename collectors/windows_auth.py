"""Forward Windows Security 4624/4625 XML to localhost or an authenticated HTTPS deployment."""
import argparse
import hashlib
import ipaddress
import json
import os
import platform
import ssl
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
ROOT = Path(__file__).resolve().parents[1]


def event_payload(xml: str) -> dict:
    """Keep the entire exported XML; normalized fields are derived from this same XML."""
    root = ET.fromstring(xml)
    system = root.find("e:System", NS)
    if system is None:
        raise ValueError("Missing Windows event System element")
    event_id = int(system.findtext("e:EventID", namespaces=NS) or 0)
    provider = system.find("e:Provider", NS)
    if event_id not in (4624, 4625) or provider is None or provider.get("Name") != "Microsoft-Windows-Security-Auditing":
        raise ValueError("Expected a Windows Security 4624 or 4625 event")
    created = system.find("e:TimeCreated", NS)
    if created is None:
        raise ValueError("Missing event time")
    dt = datetime.fromisoformat(created.attrib["SystemTime"].replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Event time must include a timezone")
    data = {e.attrib["Name"]: e.text or "" for e in root.findall("e:EventData/e:Data", NS) if "Name" in e.attrib}
    computer = system.findtext("e:Computer", namespaces=NS)
    user = data.get("TargetUserName")
    if not computer or not user or user == "-":
        raise ValueError("Missing computer or target user; refusing to fabricate identity")
    payload = {
        "source": "windows-security", "event_id": event_id,
        "record_id": int(system.findtext("e:EventRecordID", namespaces=NS) or 0),
        "timestamp": dt.astimezone(timezone.utc).isoformat(timespec="milliseconds"),
        "computer": computer, "user_name": user, "raw_xml": xml,
    }
    for original, field in (("TargetDomainName", "user_domain"), ("WorkstationName", "workstation"),
                            ("LogonType", "logon_type")):
        if data.get(original) not in (None, "", "-"):
            payload[field] = data[original]
    try:
        payload["source_ip"] = str(ipaddress.ip_address(data.get("IpAddress", "")))
    except ValueError:
        pass  # local sign-ins often have no IP; the original value remains in raw_xml
    port = data.get("IpPort", "")
    if ("source_ip" in payload or "workstation" in payload) and port.isdigit() and 0 < int(port) <= 65535:
        payload["source_port"] = int(port)
    if payload["record_id"] <= 0:
        raise ValueError("Missing event record ID")
    return payload


def read_events(after: int, since: str, limit: int = 200) -> list[str]:
    ps = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(ps), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                             str(Path(__file__).with_name("read-windows-auth.ps1")), "-AfterRecordId", str(after),
                             "-SinceUtc", since, "-MaxEvents", str(limit)], capture_output=True,
                            text=True, encoding="utf-8-sig", timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Windows event reader failed")
    events = json.loads(result.stdout)
    if not isinstance(events, list) or not all(isinstance(e, str) for e in events):
        raise ValueError("Unexpected event reader response")
    return events


def save_checkpoint(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def request_with_retry(client, method: str, url: str, **kwargs):
    """Retry temporary HTTP failures until recovery or Ctrl+C; permanent errors remain visible."""
    delay = 1
    retried = False
    while True:
        try:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            cause = exc
            while cause is not None:
                if isinstance(cause, ssl.SSLCertVerificationError):
                    raise RuntimeError("TLS certificate verification failed; use a trusted certificate or --ca-file") from exc
                cause = cause.__cause__
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                if status != 429 and not 500 <= status < 600:
                    raise
                reason = f"HTTP {status}"
            else:
                reason = type(exc).__name__
            print(f"API unavailable ({reason}); retrying in {delay}s. Ctrl+C to stop.", file=sys.stderr, flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 30)
            retried = True
            continue
        if retried:
            print("API connection recovered; resuming collection.", flush=True)
        return response


def forward(client, events: list[str], state: dict, checkpoint: Path) -> int:
    sent = 0
    for xml in events:
        payload = event_payload(xml)
        if payload["record_id"] <= state["last_record_id"]:
            continue
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        key = "windows-auth-v1:" + hashlib.sha256(line.encode("utf-8")).hexdigest()
        response = request_with_retry(client, "POST", "/api/ingest", json={"lines": [line]},
                                      headers={"Idempotency-Key": key, "X-Anvaya-Require-Live": "true"})
        if response.headers.get("Idempotency-Key") != key:
            raise RuntimeError("API lacks duplicate prevention; restart the updated pilot before collecting")
        if response.json().get("accepted") != 1:
            raise RuntimeError("Ingest did not acknowledge the record; checkpoint was not advanced")
        # A replay after a lost acknowledgement/checkpoint uses the same durable server receipt.
        next_state = {**state, "last_record_id": payload["record_id"]}
        save_checkpoint(checkpoint, next_state)
        state.update(next_state)
        sent += 1
    return sent


def local_api(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme not in ("http", "https") or not url.hostname or url.path not in ("", "/")
            or url.query or url.fragment or url.username or url.password
            or (url.scheme == "http" and url.hostname not in ("127.0.0.1", "localhost", "::1"))):
        raise argparse.ArgumentTypeError("Use an HTTPS origin; plain HTTP is allowed only on localhost")
    return value.rstrip("/")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", type=local_api, default="http://127.0.0.1:8081")
    ap.add_argument("--api-key-file", type=Path, help="Private file containing the collector API key")
    ap.add_argument("--ca-file", type=Path, help="Optional trusted CA certificate PEM for a private HTTPS server")
    ap.add_argument("--checkpoint", type=Path, default=ROOT / "data/live/windows-auth-checkpoint.json")
    ap.add_argument("--lookback-minutes", type=int, default=15)
    ap.add_argument("--poll-seconds", type=int, default=5)
    ap.add_argument("--once", action="store_true", help="Send one batch (up to 200 events), then exit")
    args = ap.parse_args(argv)
    if args.lookback_minutes < 0 or args.poll_seconds < 1:
        ap.error("lookback must be nonnegative and poll seconds must be positive")
    if sys.platform != "win32":
        ap.error("Use this collector on Windows")
    if urlsplit(args.api).hostname not in ("127.0.0.1", "localhost", "::1") and args.api_key_file is None:
        ap.error("Remote collection requires --api-key-file")
    try:
        headers = {}
        if args.api_key_file:
            key = args.api_key_file.read_text(encoding="utf-8").strip()
            if len(key) < 32 or any(c.isspace() for c in key) or not key.isascii():
                raise ValueError("Invalid collector API key file")
            headers["Authorization"] = f"Bearer {key}"
        tls = ssl.create_default_context(cafile=str(args.ca_file)) if args.ca_file else True
        if args.checkpoint.exists():
            state = json.loads(args.checkpoint.read_text(encoding="utf-8"))
            if state["computer"] != platform.node() or state["api"] != args.api:
                raise ValueError("Checkpoint belongs to a different computer or API; use a separate checkpoint")
        else:
            state = {"computer": platform.node(), "api": args.api, "last_record_id": 0,
                     "since_utc": (datetime.now(timezone.utc) - timedelta(minutes=args.lookback_minutes)).isoformat()}
        with httpx.Client(base_url=args.api, timeout=20, trust_env=False, headers=headers, verify=tls,
                          follow_redirects=False) as client:
            health = request_with_retry(client, "GET", "/api/health")
            if health.json().get("demo_mode") is not False:
                raise ValueError("Collector requires a live-mode API; refusing to mix real logs into a demo")
            while True:
                events = read_events(state["last_record_id"], state["since_utc"])
                n = forward(client, events, state, args.checkpoint)
                if not args.checkpoint.exists():
                    save_checkpoint(args.checkpoint, state)
                print(f"Forwarded {n} Windows sign-in events; checkpoint {state['last_record_id']}", flush=True)
                if args.once:
                    return 0
                if len(events) < 200:
                    time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, ET.ParseError, httpx.HTTPError, subprocess.SubprocessError) as exc:
        print(f"Collector stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
