import pytest

from app.ocsf.lineage import Trace
from app.ocsf.roundtrip import check_roundtrip, coverage
from app.parsers.registry import Pack, PackRegistry
from app.pipeline.worker import normalize
from tests.conftest import ocsf_impl
from tests.samples_text import ASA, EVE, FGT
from tests.test_parsers import envelope_for

REG = PackRegistry()
ENUMS, VALIDATE = ocsf_impl()


@pytest.mark.parametrize("name", ["cisco-asa", "suricata-eve", "fortigate-kv", "acme-edge"])
def test_golden_samples_are_lossless(name):
    _, _, out = envelope_for(name)
    assert out.event.anvaya.roundtrip.model_dump() == {"ok": True, "value_check": True, "coverage": 1.0, "dropped": 0}


def test_wrong_span_fails_value_check():
    """A lineage span that doesn't hold the extracted value (here shifted by one byte) is caught."""
    good = [Trace("dst_endpoint.ip", [(145, 154)], False, ["10.2.4.18"], ["b_ip"])]
    bad = [Trace("dst_endpoint.ip", [(146, 155)], False, ["10.2.4.18"], ["b_ip"])]
    assert check_roundtrip(ASA.encode(), "utf-8", good, [(0, len(ASA))], ["b_ip"])["ok"]
    rt = check_roundtrip(ASA.encode(), "utf-8", bad, [(0, len(ASA))], ["b_ip"])
    assert not rt["value_check"] and not rt["ok"]


def test_broken_pack_fails_coverage():
    """A pack whose rule regex stops before the end leaves bytes unaccounted, so the record is flagged."""
    yaml_text = REG.get("cisco-asa").yaml
    broken = yaml_text.replace(r" \((?P<b_mapped>[\d.]+/\d+)\)$'", r"'", 1)
    assert broken != yaml_text
    out = normalize(ASA.encode(), "r-000000000000", 1, 0, "utf-8", REG, ENUMS, VALIDATE, pack=Pack(broken))
    rt = out.event.anvaya.roundtrip
    assert not rt.ok and rt.coverage < 0.95 and out.reason == "roundtrip_fail"


def test_uncovered_bytes_lower_coverage():
    assert coverage([(0, 50)], 100) == 0.5
    assert coverage([(0, 60), (40, 100)], 100) == 1.0


def test_unextracted_tail_fails_coverage():
    """A pack whose kv extractor stops early leaves bytes unaccounted → coverage < 0.95 → not ok."""
    text = FGT + ' trailing junk that is not key value at all, many bytes of it to drop coverage below the line ' * 2
    out = normalize(text.encode(), "r-000000000000", 1, 0, "utf-8", REG, ENUMS, VALIDATE)
    assert out.event and out.reason == "roundtrip_fail" and out.event.anvaya.roundtrip.coverage < 0.95
    assert "roundtrip_fail" in out.flags


def test_eve_header_and_json_fully_accounted():
    _, _, out = envelope_for("suricata-eve")
    assert out.event.anvaya.roundtrip.coverage == 1.0 and len(EVE) == 422
