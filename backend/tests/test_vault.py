import hashlib
from datetime import date

import pytest

from app.core.clock import WallClock
from app.core.models import RawMeta
from app.ingest.http import split_body
from app.ingest.vetting import vet
from app.vault.store import SegmentRawStore
from generator.scenario import build_scripted_lines

META = RawMeta(transport="udp", peer_ip="127.0.0.1", flags=[], encoding="utf-8")


def store(tmp_path, **kw):
    return SegmentRawStore(tmp_path / "vault", WallClock(), demo=True, **kw)


def test_bytes_roundtrip(tmp_path):
    s = store(tmp_path)
    samples = [b"hello", b"\xff\xfe not utf-8 \x00\x01", b"", "नमस्ते".encode()]
    recs = [s.append(b, META) for b in samples]
    for rec, b in zip(recs, samples):
        assert s.read(rec.raw_id) == b
        assert rec.raw_sha256 == hashlib.sha256(b).hexdigest() and rec.size == len(b)
    assert [r.seq for r in recs] == [1, 2, 3, 4]
    ends = [0]
    for b in samples[:-1]:
        ends.append(ends[-1] + 4 + len(b))
    assert [r.offset for r in recs] == ends


def test_reopen_keeps_index_and_seq(tmp_path):
    s = store(tmp_path)
    a = s.append(b"one", META)
    s.close()
    s2 = store(tmp_path, index=[a])
    b = s2.append(b"two", META)
    assert b.seq == 2 and s2.read(a.raw_id) == b"one" and b.offset == 7


def test_rotation(tmp_path):
    s = store(tmp_path, segment_max=20)
    recs = [s.append(b"0123456789", META) for _ in range(3)]
    assert [r.segment for r in recs] == ["seg-000001.log", "seg-000002.log", "seg-000003.log"]
    assert all(s.read(r.raw_id) == b"0123456789" for r in recs)
    assert [r.seq for r, _ in s.iter_seq_range(1, 3)] == [1, 2, 3]


def test_overwrite_changes_exactly_one_byte(tmp_path):
    s = store(tmp_path)
    before = [s.append(b"aaaa", META), s.append(b"bbbbbbbb", META), s.append(b"cccc", META)]
    vault = (tmp_path / "vault" / "seg-000001.log").read_bytes()
    assert s.read(before[1].raw_id) == b"bbbbbbbb"  # primes the store's reader handle for this segment
    s.overwrite_byte_for_demo(before[1].raw_id, 3, ord("X"))
    after = (tmp_path / "vault" / "seg-000001.log").read_bytes()
    assert sum(x != y for x, y in zip(vault, after)) == 1 and len(vault) == len(after)
    assert s.read(before[1].raw_id) == b"bbbXbbbb"


def test_overwrite_refused_outside_demo(tmp_path):
    s = SegmentRawStore(tmp_path / "v", WallClock(), demo=False)
    rec = s.append(b"x", META)
    with pytest.raises(PermissionError):
        s.overwrite_byte_for_demo(rec.raw_id, 0, 0)


def test_raw_id_of_seq_164(tmp_path):
    s = store(tmp_path)
    recs = [s.append(t.encode(), META) for _, _, t in build_scripted_lines(date(2026, 9, 30))]
    assert recs[163].seq == 164 and recs[163].raw_id == "r-899f4edf0030"
    assert recs[163].raw_sha256 == "d12173d4509247b2d5e571a3922472f9262482d1ef617ef33b6ba152f74f4251"


@pytest.mark.parametrize("data,flags,enc", [
    (b"plain", [], "utf-8"),
    (b"a\nb", ["embedded_newline"], "utf-8"),
    (b"a\x00b", ["nul_byte"], "utf-8"),
    (b"a\x07b", ["control_chars"], "utf-8"),
    (b"\xff", ["invalid_utf8"], "binary"),
    (b"x" * 65537, ["oversized"], "utf-8"),
], ids=["plain", "newline", "nul", "control", "binary", "oversized"])
def test_vetting(data, flags, enc):
    assert vet(data) == (flags, enc)


def test_http_split():
    assert split_body(b"a\r\nb\n\nc\n", "text/plain") == [b"a", b"b", b"c"]
    assert split_body(b'{"lines":["x","y"]}', "application/json") == [b"x", b"y"]
