import pytest

from app.ocsf.confidence import score
from tests.test_parsers import envelope_for


@pytest.mark.parametrize("name,expected", [("cisco-asa", 91), ("suricata-eve", 90), ("fortigate-kv", 89),
                                           ("acme-edge", 95)])
def test_golden_scores(name, expected):
    golden, _, out = envelope_for(name)
    assert out.event.anvaya.parse_confidence == expected
    assert out.event.anvaya.confidence_breakdown == golden["anvaya"]["confidence_breakdown"]


def test_formula_and_round_half_up():
    assert score(e=16, m=9, r_present=3, r_total=3, t_ok=4, t_total=4)[0] == 91
    assert score(e=4, m=1, r_present=1, r_total=2, t_ok=0, t_total=0)[0] == 60   # 25 + 30 + 5
    assert score(e=8, m=1, r_present=1, r_total=1, t_ok=1, t_total=2)[0] == 68   # 50 + 15 + 2.5 → 67.5 → 68
    assert score(e=1, m=1, r_present=1, r_total=1, t_ok=1, t_total=1, fingerprint_confidence=0.5)[0] == 60
