import json

from app.delivery.retention import STATEMENT, build_report
from tests.conftest import ingest_scenario


def test_statement_exact_and_honest(c):
    ingest_scenario(c)
    c.worker.drain()
    c.ledger.verify_all()
    r = build_report(c.repo, 1)
    assert r["statement"] == "ANVAYA's tamper-evident retention supports CERT-In's 180-day log retention requirement."
    assert r["statement"] == STATEMENT and r["retention_target_days"] == 180
    text = json.dumps(r).lower()
    assert "certified" not in text and "compliant" not in text
    src = {s["device"]: s for s in r["sources"]}
    assert src["fw01"]["records"] == 104 and src["ids01"]["records"] == 33 and src["vpn01"]["records"] == 70
    assert not all(s["sealed"] for s in r["sources"])  # seq 193–207 still wait for the age seal
    c.ledger.seal()
    assert all(s["sealed"] for s in build_report(c.repo, 1)["sources"])
    assert r["ledger"]["verdict"] == "verified" and r["note"].startswith("Synthetic lab data.")


def test_report_before_any_verify(c):
    r = build_report(c.repo, 1)
    assert r["sources"] == [] and r["ledger"] == {"verdict": None, "last_verified": None}
