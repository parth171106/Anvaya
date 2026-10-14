"""Sanitized SSH fixtures, not real user log records."""
import json
from datetime import datetime

import httpx
import pytest

from app.parsers.registry import PackRegistry
from app.pipeline.worker import normalize
from collectors.linux_ssh import deliver, journal_command, journal_line
from tests.conftest import ocsf_impl


def entry(message="Accepted publickey for ubuntu from 198.51.100.40 port 24778 ssh2: RSA SHA256:test", **fields):
    return {"MESSAGE": message, "__CURSOR": "s=test;i=1", "__REALTIME_TIMESTAMP": "1791879692000000",
            "_HOSTNAME": "ec2-test", "SYSLOG_IDENTIFIER": "sshd", "_PID": "123", **fields}


@pytest.mark.parametrize("message,status,user,ip", [
    ("Invalid user anvaya-check from 198.51.100.40 port 55430", "Failure", "anvaya-check", "198.51.100.40"),
    ("Accepted publickey for ubuntu from 198.51.100.40 port 24778 ssh2: RSA SHA256:test", "Success", "ubuntu", "198.51.100.40"),
    ("Accepted password for alice from 2001:db8::1 port 2222 ssh2", "Success", "alice", "2001:db8::1"),
    ("Failed publickey for invalid user fake from 198.51.100.40 port 3210 ssh2: RSA SHA256:test [preauth]", "Failure", "fake", "198.51.100.40"),
    ("Failed password for root from 198.51.100.40 port 3211 ssh2", "Failure", "root", "198.51.100.40"),
    ("Failed keyboard-interactive/pam for alice from 2001:db8::2 port 3212 ssh2", "Failure", "alice", "2001:db8::2"),
])
def test_real_format_auth_fields_and_roundtrip(message, status, user, ip):
    text = journal_line(entry(message))
    enums, validate = ocsf_impl()
    out = normalize(text.encode(), "r-test", 1, 0, "utf-8", PackRegistry(), enums, validate)
    assert out.reason is None
    assert out.event.anvaya.roundtrip.ok and out.event.anvaya.lineage
    assert out.event.ocsf["status"] == status
    assert out.event.ocsf["user"]["name"] == user
    assert out.event.ocsf["src_endpoint"]["ip"] == ip
    assert out.event.ocsf["raw_data"] == text
    assert out.event.ocsf["time"] == 1791879692000


def test_sample_timezone_and_newer_sshd_name():
    text = "2026-10-13T13:51:32+05:30 ec2-test sshd-session[123]: Accepted publickey for ubuntu from 198.51.100.40 port 22 ssh2"
    enums, validate = ocsf_impl()
    out = normalize(text.encode(), "r-test", 1, 0, "utf-8", PackRegistry(), enums, validate)
    assert out.event.ocsf["time"] == int(datetime.fromisoformat("2026-10-13T08:21:32+00:00").timestamp() * 1000)


@pytest.mark.parametrize("message", ["Server listening on 0.0.0.0 port 22.",
    "pam_unix(sshd:session): session opened for user ubuntu(uid=1000) by ubuntu(uid=0)",
    "Received signal 15; terminating."])
def test_lifecycle_and_pam_are_not_duplicate_logins(message):
    assert journal_line(entry(message)) is None


def test_unsupported_auth_is_retained_for_quarantine():
    text = journal_line(entry("Failed unusual new format"))
    enums, validate = ocsf_impl()
    assert text.endswith("Failed unusual new format")
    assert normalize(text.encode(), "r-test", 1, 0, "utf-8", PackRegistry(), enums, validate).reason == "parse_error"


def test_missing_metadata_stops_without_fabricating_fields():
    with pytest.raises(ValueError):
        journal_line(entry(_HOSTNAME=""))
    with pytest.raises(ValueError):
        journal_line(entry(MESSAGE=[1, 2]))


def test_acknowledged_cursor_and_stable_receipt(tmp_path):
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(202, headers={"Idempotency-Key": req.headers["Idempotency-Key"]}, json={"accepted": 1})
    state = {"machine_id": "test-machine"}
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test") as client:
        deliver(client, entry(), state, tmp_path / "cursor.json")
        deliver(client, entry(), state, tmp_path / "cursor.json")
    assert state["cursor"] == entry()["__CURSOR"]
    assert json.loads((tmp_path / "cursor.json").read_text())["cursor"] == state["cursor"]
    assert requests[0].headers["Idempotency-Key"] == requests[1].headers["Idempotency-Key"]


@pytest.mark.parametrize("status,headers,body", [(401, {}, {}), (202, {}, {"accepted": 1})])
def test_failed_ack_does_not_advance_cursor(tmp_path, status, headers, body):
    state = {"machine_id": "test-machine", "cursor": "old"}
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, headers=headers, json=body)), base_url="https://example.test") as client:
        with pytest.raises((httpx.HTTPStatusError, RuntimeError)):
            deliver(client, entry(), state, tmp_path / "cursor.json")
    assert state["cursor"] == "old" and not (tmp_path / "cursor.json").exists()


def test_checkpoint_failure_retries_same_receipt(tmp_path, monkeypatch):
    import collectors.linux_ssh as collector
    state = {"machine_id": "test-machine", "cursor": "old"}
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(collector, "save_checkpoint", fail)
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(202, headers={"Idempotency-Key": req.headers["Idempotency-Key"]}, json={"accepted": 1})), base_url="https://example.test") as client:
        with pytest.raises(OSError):
            deliver(client, entry(), state, tmp_path / "cursor.json")
    assert state["cursor"] == "old"


def test_resume_command_does_not_drop_backlog():
    command = journal_command({"cursor": "saved", "since": "yesterday"}, False)
    assert "--after-cursor=saved" in command and "--no-tail" in command
    assert not any(arg.startswith("--since") for arg in command)
    assert "--follow" not in journal_command({"since": "yesterday"}, True)


def test_single_success_is_not_an_intrusion(c):
    c.ingest(journal_line(entry()).encode(), "http", "127.0.0.1")
    c.worker.drain()
    assert c.repo.incidents() == []
    assert c.repo.sources()[0]["events_total"] == 1
