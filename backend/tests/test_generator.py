import hashlib
import itertools
from collections import Counter
from datetime import date
from pathlib import Path

from generator.br01 import build_br01_lines
from generator.formats import at
from generator.scenario import build_scripted_lines, steady_lines

D = date(2026, 9, 30)
ASA = ('<166>Sep 30 2026 10:07:12 fw01 : %ASA-6-302013: Built inbound TCP connection 77801 for outside:198.51.100.9/40133 '
       '(198.51.100.9/40133) to inside:10.2.4.18/443 (10.2.4.18/443)')
EVE = ('<134>Sep 30 10:02:05 ids01 suricata[2211]: {"timestamp":"2026-09-30T10:02:05.000000+0530","flow_id":1500000000000900,'
       '"in_iface":"eth1","event_type":"alert","src_ip":"198.51.100.9","src_port":40100,"dest_ip":"10.2.4.18","dest_port":22,'
       '"proto":"TCP","alert":{"action":"allowed","gid":1,"signature_id":9000001,"rev":1,"signature":"ANVAYA-LAB SCAN Inbound '
       'TCP port sweep","category":"Attempted Information Leak","severity":2}}')
FGT = ('<185>date=2026-09-30 time=10:05:00 devname="vpn01" devid="FGVM01TM00000001" logid="0101039426" type="event" '
       'subtype="vpn" level="alert" vd="root" logdesc="SSL VPN login fail" action="ssl-login-fail" tunneltype="ssl-web" '
       'remip=198.51.100.9 user="admin" reason="sslvpn_login_permission_denied" msg="SSL VPN user login failed"')
EDGE = 'EDGE|2026-09-30 10:13:06|br01|SESSION|ALLOW|tcp|10.2.4.31|52300|203.0.113.12|443|bytes=1200|rule=R-110'


def raw_id(seq, text):
    return "r-" + hashlib.sha256(seq.to_bytes(8, "big") + hashlib.sha256(text.encode()).digest()).hexdigest()[:12]


def test_counts():
    lines = build_scripted_lines(D)
    assert len(lines) == 207
    assert Counter(dev for _, dev, _ in lines) == {"fw01": 104, "ids01": 33, "vpn01": 70}


def test_checkpoints():
    lines = [t for _, _, t in build_scripted_lines(D)]
    assert lines[164 - 1] == ASA and lines[40 - 1] == EVE and lines[100 - 1] == FGT
    for seq, rid in ((40, "r-64f70aaee53f"), (100, "r-3db59309ddaa"), (164, "r-899f4edf0030"), (180, "r-cc9f90d79b5a")):
        assert raw_id(seq, lines[seq - 1]) == rid


def test_order_and_window():
    lines = build_scripted_lines(D)
    assert lines == sorted(lines, key=lambda x: x[0])
    assert lines[0][0] == at(D, 10, 0) and lines[-1][0] == at(D, 10, 11, 48)


def test_br01():
    lines = build_br01_lines(at(D, 10, 14, 3))
    assert len(lines) == 20 and lines[0] == EDGE
    assert [i for i, ln in enumerate(lines) if "|DENY|" in ln] == [4, 11, 17]
    assert all(ln.count("|") == 11 for ln in lines)


def test_steady_is_benign():
    for ms, dev, text in itertools.islice(steady_lines(at(D, 10, 12)), 3000):
        assert "198.51.100.9" not in text and "10.2.4.18" not in text
        assert "Deny" not in text and "ssl-login-fail" not in text


def test_steady_cadence():
    first = list(itertools.islice(steady_lines(at(D, 10, 12)), 12))
    t = at(D, 10, 12)
    assert [(ms - t, dev) for ms, dev, _ in first[:6]] == [
        (0, "fw01"), (1000, "fw01"), (2000, "fw01"), (2000, "ids01"), (3000, "fw01"), (3000, "vpn01")]


def test_no_random_import():
    for f in (Path(__file__).parents[2] / "generator").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert "import random" not in src and "from random" not in src, f
