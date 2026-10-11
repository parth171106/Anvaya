from app.parsers.syslog_header import ByteOffsets, split
from tests.samples_text import ASA, EDGE, EVE, FGT


def test_asa_header():
    hs = split(ASA)
    assert hs.pattern_id == "asa3164y"
    assert hs.fields["pri"] == ("166", (1, 4))
    assert hs.fields["ts"] == ("Sep 30 2026 10:07:12", (5, 25))
    assert hs.fields["host"] == ("fw01", (26, 30))
    assert ASA[hs.body_offset:].startswith("%ASA-6-302013: ")


def test_suricata_header():
    hs = split(EVE)
    assert hs.pattern_id == "bsd3164"
    assert hs.fields["host"] == ("ids01", (21, 26))
    assert hs.fields["ts"] == ("Sep 30 10:02:05", (5, 20))
    assert hs.fields["app"] == ("suricata", (27, 35)) and hs.fields["pid"] == ("2211", (36, 40))
    assert EVE[hs.body_offset] == "{"


def test_bsd_single_digit_day():
    hs = split("<134>Oct  2 10:02:05 ids01 suricata[2211]: {}")
    assert hs.pattern_id == "bsd3164" and hs.fields["ts"][0] == "Oct  2 10:02:05"


def test_fortigate_pri_only():
    hs = split(FGT)
    assert hs.pattern_id == "pri_only" and hs.fields == {"pri": ("185", (1, 4))} and hs.body_offset == 5


def test_no_header():
    hs = split(EDGE)
    assert hs.pattern_id == "none" and hs.body_offset == 0


def test_byte_offsets_non_ascii():
    bo = ByteOffsets("aé b")
    assert [bo(i) for i in range(5)] == [0, 1, 3, 4, 5]
    assert ByteOffsets("plain")(3) == 3
