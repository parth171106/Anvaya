import pytest

from app.parsers import jsonspan
from app.parsers.engine import ParseFailure, parse_with_pack
from app.parsers.registry import Pack, PackError, PackRegistry
from app.parsers.syslog_header import split
from tests.samples_text import ASA, EDGE, EVE, FGT

REG = PackRegistry()


def parse(text):
    hs = split(text)
    pack = REG.detect(hs, text)
    return pack, parse_with_pack(pack, text, hs)


def spans(res):
    return {v.name: v.span for v in res.values}


def test_detection_order():
    assert [p.name for p in REG.packs] == ["suricata-eve", "fortigate-kv", "cisco-asa", "openssh-journal", "windows-security"]
    assert [parse(t)[0].name for t in (ASA, EVE, FGT)] == ["cisco-asa", "suricata-eve", "fortigate-kv"]
    assert REG.detect(split(EDGE), EDGE) is None


def test_asa_spans():
    pack, res = parse(ASA)
    s = spans(res)
    assert res.rule.id == "asa-302013-inbound" and res.selector.name == "asa_message_id"
    assert s["b_ip"] == (145, 154) and s["a_ip"] == (95, 107) and s["conn_id"] == (77, 82)
    assert s["a_port"] == (108, 113) and s["b_port"] == (155, 158) and s["direction"] == (54, 61)
    assert s["asa_message_id"] == (40, 46) and s["b_mapped"] == (160, 173) and s["a_zone"] == (87, 94)
    assert len(res.values) == 16
    assert all(ASA[a:b] == v.text for v in res.values for a, b in [v.span])


def test_suricata_json_spans():
    _, res = parse(EVE)
    s = spans(res)
    assert s["alert.signature"] == (328, 366) and s["src_ip"] == (166, 178) and s["timestamp"] == (57, 88)
    assert s["flow_id"] == (100, 116) and s["alert.severity"] == (419, 420) and s["alert.category"] == (380, 406)
    assert s["event_type"] == (149, 154) and s["alert.signature_id"] == (299, 306)
    assert res.selector.name == "event_type" and len(res.values) == 21
    assert res.accounted[-1] == (43, len(EVE))


def test_fortigate_kv_spans():
    _, res = parse(FGT)
    s = spans(res)
    assert s["user"] == (245, 250) and s["remip"] == (226, 238) and s["date"] == (10, 20) and s["time"] == (26, 34)
    assert s["msg"] == (297, 322) and s["action"] == (183, 197) and s["devid"] == (58, 74)
    assert res.selector.name == "action" and res.rule.id == "fgt-ssl-login-fail" and len(res.values) == 17
    assert res.accounted == [(0, 5), (5, len(FGT))]


def test_delimited_spans():
    pack = Pack((REG.builtin_dir.parents[1] / "aiparser" / "acme-edge.fallback.yaml").read_text(encoding="utf-8"))
    hs = split(EDGE)
    assert pack.detects(hs, EDGE)
    res = parse_with_pack(pack, EDGE, hs)
    s = spans(res)
    assert s["marker"] == (0, 4) and s["ts"] == (5, 24) and s["src_ip"] == (48, 57) and s["rule_kv"] == (92, 102)
    assert res.selector.name == "verdict" and res.accounted == [(0, len(EDGE))]


def test_json_scanner_nested_and_arrays():
    vals, end = jsonspan.scan('{"a":{"b":"x\\"y"},"c":[1,true,null]}')
    assert [(p, raw) for p, raw, _, _ in vals] == [("a.b", 'x\\"y'), ("c[0]", "1"), ("c[1]", "true"), ("c[2]", "null")]
    assert vals[0][2] == 'x"y' and end == 36


def test_no_rule_and_parse_error():
    unknown = "<166>Sep 30 2026 10:07:12 fw01 : %ASA-6-999999: Something else"
    with pytest.raises(ParseFailure) as e:
        parse(unknown)
    assert e.value.reason == "no_rule"
    broken = ASA.replace("Built inbound TCP", "Built inbound XYZ")
    with pytest.raises(ParseFailure) as e:
        parse(broken)
    assert e.value.reason == "parse_error"


def test_bad_pack_rejected():
    with pytest.raises(PackError):
        Pack("name: x\nversion: 1\n")
    with pytest.raises(PackError):
        Pack("{name: x, version: 1, priority: 1, vendor: a, product: b, format: f, detect: {}, required: [],"
             " extractor: {type: xml}, rules: []}")
