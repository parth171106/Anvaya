"""In-process witness stores (SIM, TRD.md §8.4). Each has its own key and SQLite file; HTTP witnesses later."""
import sqlite3
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ZERO = bytes(32)
LABELS = {"witness-ntro": "NTRO witness · simulated, local", "witness-certin": "CERT-In witness · simulated, local"}


class WitnessRejected(Exception):
    pass


class InProcessWitness:
    def __init__(self, name: str, db_path: Path, key: Ed25519PrivateKey):
        self.name, self.key = name, key
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.con.execute("CREATE TABLE IF NOT EXISTS heads(batch_id INTEGER PRIMARY KEY, head TEXT NOT NULL,"
                         " prev_head TEXT NOT NULL, primary_sig TEXT NOT NULL, cosig TEXT NOT NULL,"
                         " received_at INTEGER NOT NULL)")

    def cosign(self, batch_id: int, head: bytes, prev_head: bytes, primary_sig: bytes, primary_pub: bytes) -> bytes:
        try:
            Ed25519PublicKey.from_public_bytes(primary_pub).verify(primary_sig, head)
        except InvalidSignature:
            raise WitnessRejected("bad_signature")
        expected_prev = ZERO if batch_id == 1 else self.head_for(batch_id - 1)
        if prev_head != expected_prev:
            raise WitnessRejected("prev_head_gap")
        cosig = self.key.sign(head)
        try:  # primary key on batch_id: an existing batch can never be overwritten
            self.con.execute("INSERT INTO heads VALUES (?,?,?,?,?,?)", (batch_id, head.hex(), prev_head.hex(),
                             primary_sig.hex(), cosig.hex(), int(time.time() * 1000)))
        except sqlite3.IntegrityError:
            raise WitnessRejected("batch_exists")
        return cosig

    def head_for(self, batch_id: int) -> bytes | None:
        r = self.con.execute("SELECT head FROM heads WHERE batch_id=?", (batch_id,)).fetchone()
        return bytes.fromhex(r[0]) if r else None

    def last_batch(self) -> int:
        return self.con.execute("SELECT COALESCE(MAX(batch_id), 0) FROM heads").fetchone()[0]

    def close(self) -> None:
        self.con.close()
