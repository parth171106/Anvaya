from generator.formats import at
from generator.scenario import build_scripted_lines
from tests.conftest import D, ingest_scenario


def collect(c):
    seen = []
    c.publish = lambda e, d: seen.append((e, d))
    return seen


def test_scenario_yields_one_high_incident(c):
    ingest_scenario(c)
    c.worker.drain()
    incs = c.repo.incidents()
    assert len(incs) == 1
    i = incs[0]
    assert (i["incident_id"], i["attacker_ip"], i["target_ip"], i["risk"], i["level"]) == \
        ("inc-0001", "198.51.100.9", "10.2.4.18", 95, "High")
    assert i["stages"] == ["recon", "credential", "access"] and i["event_count"] == 56
    assert i["devices"] == ["fw01", "ids01", "vpn01"]
    assert (i["first_time"], i["last_time"]) == (at(D, 10, 2), at(D, 10, 7, 12))
    assert i["title"] == "Coordinated intrusion attempt: 198.51.100.9 → 10.2.4.18"
    d = c.correlator.detail("inc-0001")
    assert d["risk_breakdown"] == {"stages": 75, "devices": 10, "ordered": 10}
    assert [s["headline"] for s in d["stages_detail"]] == [
        "Port sweep of 12 ports on 10.2.4.18; 3 IDS scan alerts",
        "40 failed VPN logins from 198.51.100.9 (admin, root, vpnuser, administrator)",
        "Firewall allowed 198.51.100.9 → 10.2.4.18:443"]
    assert [(s["label"], s["event_count"], s["devices"]) for s in d["stages_detail"]] == [
        ("Reconnaissance", 15, ["fw01", "ids01"]), ("Credential attack", 40, ["vpn01"]), ("Access", 1, ["fw01"])]


def test_opened_at_tenth_failure_then_updated_to_95(c):
    seen = collect(c)
    for rec in ingest_scenario(c):
        c.worker.process([c.queue.get_nowait()])   # one record per batch, as in a live run
    opened = [(e, d) for e, d in seen if e.startswith("incident.")]
    assert [e for e, _ in opened] == ["incident.opened", "incident.updated"]
    assert opened[0][1]["risk"] == 70 and opened[0][1]["stages"] == ["recon", "credential"]
    assert opened[0][1]["last_time"] == at(D, 10, 5, 9)  # the 10th failure
    assert opened[1][1]["risk"] == 95 and opened[1][1]["last_time"] == at(D, 10, 7, 12)


def test_noise_only_yields_nothing(c):
    for _, _, text in build_scripted_lines(D):
        if "198.51.100.9" not in text:
            c.ingest(text.encode(), "udp", "127.0.0.1")
    c.worker.drain()
    assert c.repo.incidents() == []


def test_replay_is_idempotent(c):
    seen = collect(c)
    recs = ingest_scenario(c)
    c.worker.drain()
    n = sum(1 for e, _ in seen if e.startswith("incident."))
    c.replays.start([r.raw_id for r in recs])
    c.worker.drain()
    c.replays.start([r.raw_id for r in recs])
    c.worker.drain()
    assert len(c.repo.incidents()) == 1 and c.repo.incidents()[0]["event_count"] == 56
    assert sum(1 for e, _ in seen if e.startswith("incident.")) == n
