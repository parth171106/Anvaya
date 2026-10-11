"""Append-only raw vault: [u32 BE length][bytes] records in rotating segment files (BACKEND_SCHEMA.md §3)."""
import hashlib
import os
import struct
import time
from pathlib import Path
from typing import Iterable, Iterator

from app.core.ids import raw_id
from app.core.models import RawMeta, RawRecord

SEGMENT_MAX = 64 * 1024 * 1024


class SegmentRawStore:
    def __init__(self, vault_dir: Path, clock, index: Iterable[RawRecord] = (), demo: bool = False,
                 segment_max: int = SEGMENT_MAX):
        self.dir = Path(vault_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.clock, self.demo, self.segment_max = clock, demo, segment_max
        self._by_seq: dict[int, RawRecord] = {}
        self._by_id: dict[str, RawRecord] = {}
        for rec in index:
            self._index(rec)
        self.last_seq = max(self._by_seq, default=0)
        segs = sorted(self.dir.glob("seg-*.log"))
        self.segment = segs[-1].name if segs else "seg-000001.log"
        self._f = open(self.dir / self.segment, "ab")
        self._readers: dict[str, object] = {}
        self._unsynced, self._last_sync = 0, time.monotonic()

    def _index(self, rec: RawRecord) -> None:
        self._by_seq[rec.seq] = rec
        self._by_id[rec.raw_id] = rec

    def append(self, data: bytes, meta: RawMeta) -> RawRecord:
        if self._f.tell() + 4 + len(data) > self.segment_max and self._f.tell() > 0:
            self._rotate()
        seq = self.last_seq + 1
        sha = hashlib.sha256(data).digest()
        offset = self._f.tell()
        self._f.write(struct.pack(">I", len(data)) + data)
        self._f.flush()  # visible to readers now; fsync is batched below
        self.last_seq = seq
        rec = RawRecord(raw_id=raw_id(seq, sha), seq=seq, raw_sha256=sha.hex(), size=len(data), segment=self.segment,
                        offset=offset, received_at=self.clock.now_ms(), wall_received_at=int(time.time() * 1000),
                        meta=meta)
        self._index(rec)
        self._unsynced += 1
        if self._unsynced >= 16 or time.monotonic() - self._last_sync >= 0.25:
            self.sync()
        return rec

    def sync(self) -> None:
        if self._unsynced:
            os.fsync(self._f.fileno())
            self._unsynced, self._last_sync = 0, time.monotonic()

    def _rotate(self) -> None:
        self.sync()
        self._f.close()
        n = int(self.segment[4:10]) + 1
        self.segment = f"seg-{n:06d}.log"
        self._f = open(self.dir / self.segment, "ab")

    def record(self, raw_id_: str) -> RawRecord:
        return self._by_id[raw_id_]  # KeyError → caller maps to 404

    def _read_at(self, rec: RawRecord) -> bytes:
        f = self._readers.get(rec.segment)
        if f is None:
            # unbuffered: a demo tamper rewrites bytes through another handle and must be seen at once
            f = self._readers[rec.segment] = open(self.dir / rec.segment, "rb", buffering=0)
        f.seek(rec.offset)
        (n,) = struct.unpack(">I", f.read(4))
        return f.read(n)

    def read(self, raw_id_: str) -> bytes:
        return self._read_at(self._by_id[raw_id_])

    def iter_seq_range(self, first_seq: int, last_seq: int) -> Iterator[tuple[RawRecord, bytes]]:
        for seq in range(first_seq, last_seq + 1):
            rec = self._by_seq[seq]
            yield rec, self._read_at(rec)

    def overwrite_byte_for_demo(self, raw_id_: str, offset: int, value: int) -> None:
        if not self.demo:
            raise PermissionError("overwrite_byte_for_demo is only available in DEMO_MODE")
        rec = self._by_id[raw_id_]
        if not 0 <= offset < rec.size:
            raise ValueError("offset outside the record")
        self.sync()
        with open(self.dir / rec.segment, "r+b") as f:
            f.seek(rec.offset + 4 + offset)
            f.write(bytes([value]))
            f.flush()
            os.fsync(f.fileno())

    @property
    def closed(self) -> bool:
        return self._f.closed

    def close(self) -> None:
        self.sync()
        self._f.close()
        for f in self._readers.values():
            f.close()
        self._readers.clear()
