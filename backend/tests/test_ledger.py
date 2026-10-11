import json

from app.vault.ledger import TAMPER_OFFSET, TAMPER_VALUE
from tests.conftest import ingest_scenario


def fake_event(c, rec, text):
    """Stand-in for the parse-time copy (events.ocsf.raw_data + lineage); the pipeline writes the real one."""
    lineage = [{"path": "dst_endpoint.ip", "spans": [[145, 154]], "derived": False},
               {"path": "unmapped.dst_mapped", "spans": [[160, 173]], "derived": False}]
    c.repo.con.execute(
        "INSERT INTO events VALUES (?,?,?,?,'fw01','Cisco','ASA','cisco-asa-syslog',4001,'Network Activity','Open',"
        "NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'Informational',NULL,91,'cisco-asa@1.0.0','r',1,1.0,?,?)",
        ("e-" + rec.raw_id[2:], rec.raw_id, rec.seq, rec.received_at, json.dumps({"raw_data": text}),
         json.dumps({"lineage": lineage})))


def test_count_triggered_batches(c):
    recs = ingest_scenario(c)
    assert c.repo.get_raw(recs[163].raw_id).batch_id == 11
    assert c.repo.get_raw(recs[39].raw_id).batch_id == 3
    assert c.repo.batch(3)["first_seq"] == 33 and c.repo.batch(3)["last_seq"] == 48
    assert c.repo.last_batch()["batch_id"] == 12 and len(c.ledger.unsealed) == 15
    assert c.repo.cosigned_batches() == 12


def test_verify_tamper_reseal(c):
    recs = ingest_scenario(c)
    target = c.ledger.tamper_target()
    assert target.raw_id == recs[163].raw_id == "r-899f4edf0030"
    fake_event(c, target, c.store.read(target.raw_id).decode())

    r = c.ledger.verify_all()
    assert r["verdict"] == "verified" and r["checked_batches"] == 12 and r["checked_records"] == 192
    assert all(w["agree"] for w in r["witness_status"])
    ok = c.ledger.verify_record("r-64f70aaee53f")
    assert ok["ok"] and ok["batch_id"] == 3 and ok["leaf_index"] == 7 and len(ok["audit_path"]) == 4

    c.store.overwrite_byte_for_demo(target.raw_id, TAMPER_OFFSET, TAMPER_VALUE)
    r = c.ledger.verify_all()
    assert r["verdict"] == "tampered"
    assert len(r["failed_records"]) == 1
    f = r["failed_records"][0]
    assert (f["raw_id"], f["seq"], f["batch_id"], f["first_diff_offset"]) == ("r-899f4edf0030", 164, 11, 153)
    assert f["changed"] == {"from": "8", "to": "9"} and f["field"] == "dst_endpoint.ip"
    assert r["failed_batches"] == [{"batch_id": 11, "reason": "leaf_mismatch"}]
    bad = c.ledger.verify_record(target.raw_id)
    assert not bad["ok"] and bad["first_diff_offset"] == 153 and not bad["root_ok"]
    print(json.dumps({k: v for k, v in r.items() if k != "took_ms"}, indent=1))

    assert c.ledger.reseal_from(11) == [11, 12]
    r = c.ledger.verify_all()
    assert r["verdict"] == "witness_mismatch" and r["failed_records"] == [] and r["failed_batches"] == []
    assert [(w["agree"], w["mismatched_batches"]) for w in r["witness_status"]] == [(False, [11, 12])] * 2


def test_age_seal(c):
    rec = c.ingest(b"one line", "http", "127.0.0.1")
    c.ledger.tick()
    assert c.repo.get_raw(rec.raw_id).batch_id is None
    c.ledger.unsealed[0] = rec.model_copy(update={"wall_received_at": rec.wall_received_at - 6000})
    c.ledger.tick()
    assert c.repo.get_raw(rec.raw_id).batch_id == 1
