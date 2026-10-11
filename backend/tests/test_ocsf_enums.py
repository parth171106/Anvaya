"""The enum ids ANVAYA uses (TRD.md §7.3's expected table) match the vendored schema, and goldens use them."""
import json
from pathlib import Path

from app.ocsf.enums import Enums

E = Enums()
SAMPLES = Path(__file__).with_name("samples")


def test_expected_ids():
    assert {s: E.id_for(4001, "severity_id", s) for s in ("Informational", "Low", "Medium", "High")} == \
        {"Informational": 1, "Low": 2, "Medium": 3, "High": 4}
    assert {a: E.id_for(4001, "activity_id", a) for a in ("Open", "Close", "Refuse", "Traffic")} == \
        {"Open": 1, "Close": 2, "Refuse": 5, "Traffic": 6}
    assert E.id_for(3002, "activity_id", "Logon") == 1 and E.id_for(2004, "activity_id", "Create") == 1
    assert (E.id_for(3002, "status_id", "Success"), E.id_for(3002, "status_id", "Failure")) == (1, 2)
    assert (E.id_for(4001, "action_id", "Allowed"), E.id_for(4001, "action_id", "Denied")) == (1, 2)
    assert (E.id_for(4001, "disposition_id", "Allowed"), E.id_for(4001, "disposition_id", "Blocked")) == (1, 2)
    assert (E.direction_id("Inbound"), E.direction_id("Outbound"), E.direction_id("Unknown")) == (1, 2, 0)
    assert (E.observable_type("IP Address"), E.observable_type("User Name")) == (2, 4)


def test_classes():
    assert E.class_info(4001) == ("Network Activity", 4, "Network Activity")
    assert E.class_info(2004) == ("Detection Finding", 2, "Findings")
    assert E.class_info(3002) == ("Authentication", 3, "Identity & Access Management")


def test_goldens_use_schema_ids():
    for name in ("cisco-asa", "suricata-eve", "fortigate-kv", "acme-edge"):
        o = json.loads((SAMPLES / name / f"{name}.json").read_text(encoding="utf-8"))["ocsf"]
        cls = o["class_uid"]
        assert o["activity_id"] == E.id_for(cls, "activity_id", o["activity_name"])
        assert o["severity_id"] == E.id_for(cls, "severity_id", o["severity"])
        assert o["type_uid"] == cls * 100 + o["activity_id"]
        for attr in ("action", "disposition", "status"):
            if attr in o:
                assert o[f"{attr}_id"] == E.id_for(cls, f"{attr}_id", o[attr])
        assert o["device"]["type_id"] == E.device_type_id(o["device"]["type"])
