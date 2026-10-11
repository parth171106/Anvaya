"""Batch sealing, Ed25519 heads, witness co-signing, verify, tamper and insider re-seal (TRD.md §8)."""
import hashlib
import time

from cryptography.exceptions import InvalidSignature

from app.core.models import RawRecord
from app.ocsf.lineage import field_at
from app.vault.keys import fingerprint, pub_bytes
from app.vault.merkle import audit_path, leaf_hash, mth, root_from_path
from app.vault.witness import ZERO, WitnessRejected

TAMPER_SEQ, TAMPER_OFFSET, TAMPER_VALUE = 164, 153, 0x39  # fw01 access event; the final '8' of 10.2.4.18 → '9'


def make_head(batch_id: int, root: bytes, prev_head: bytes) -> bytes:
    return hashlib.sha256(b"ANVAYA-HEAD-v1" + batch_id.to_bytes(8, "big") + root + prev_head).digest()


def _wall_ms() -> int:
    return int(time.time() * 1000)


def first_diff(a: bytes, b: bytes) -> int | None:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


class Ledger:
    def __init__(self, repo, store, keys, witnesses, clock, cfg, publish=lambda event, data: None):
        self.repo, self.store, self.clock, self.cfg, self.publish = repo, store, clock, cfg, publish
        self.key, self.witnesses = keys["primary"], witnesses
        self.pub = pub_bytes(self.key)
        self.fp = fingerprint(self.key)
        self.unsealed: list[RawRecord] = repo.unsealed_raw()

    # ---- sealing (FL-02) ----------------------------------------------------------------------------------------
    def add(self, rec: RawRecord) -> None:
        self.unsealed.append(rec)
        if len(self.unsealed) >= self.cfg.seal_batch_size:
            self.seal()

    def tick(self) -> None:
        """Every 250 ms: fsync the vault and seal a partial batch whose oldest record is too old."""
        self.store.sync()
        if self.unsealed and self._too_old(self.unsealed[0]):
            self.seal()

    def _too_old(self, rec: RawRecord) -> bool:
        if getattr(self.clock, "phase", None) == "scripted":
            return self.clock.now_ms() - rec.received_at >= self.cfg.seal_max_age_scripted_scn_s * 1000
        return _wall_ms() - rec.wall_received_at >= self.cfg.seal_max_age_s * 1000

    def seal(self) -> None:
        batch = self.unsealed[: self.cfg.seal_batch_size]
        root = mth([leaf_hash(bytes.fromhex(r.raw_sha256), r.seq) for r in batch])
        last = self.repo.last_batch()
        batch_id = last["batch_id"] + 1 if last else 1
        prev = bytes.fromhex(last["head"]) if last else ZERO
        head = make_head(batch_id, root, prev)
        sig = self.key.sign(head)
        now = _wall_ms()
        cosigned = 0
        with self.repo.tx():
            self.repo.insert_batch(dict(batch_id=batch_id, first_seq=batch[0].seq, last_seq=batch[-1].seq,
                                        leaf_count=len(batch), merkle_root=root.hex(), prev_head=prev.hex(),
                                        head=head.hex(), signature=sig.hex(), pubkey_fp=self.fp, sealed_at=now))
            for w in self.witnesses:
                try:
                    cosig = w.cosign(batch_id, head, prev, sig, self.pub)
                    self.repo.insert_witness_sig(batch_id, w.name, "cosigned", head.hex(), cosig.hex(), None, now)
                    cosigned += 1
                except WitnessRejected as e:
                    self.repo.insert_witness_sig(batch_id, w.name, "rejected", head.hex(), None, str(e), now)
        del self.unsealed[: len(batch)]
        self.publish("ledger.sealed", {"batch_id": batch_id, "first_seq": batch[0].seq, "last_seq": batch[-1].seq,
                                       "leaf_count": len(batch), "cosigned": cosigned})

    # ---- verify (§8.5) ------------------------------------------------------------------------------------------
    def _failed_record(self, raw_id, seq, batch_id, data: bytes) -> dict:
        ev = self.repo.event_evidence(raw_id)
        rec = dict(raw_id=raw_id, event_id=None, seq=seq, batch_id=batch_id, device=None, time=None,
                   first_diff_offset=None, changed=None, field=None)
        if ev:
            original, lineage, rec["event_id"], rec["device"], rec["time"] = ev
            off = first_diff(original, data)
            if off is not None:
                rec["first_diff_offset"] = off
                rec["changed"] = {"from": original[off:off + 1].decode("latin-1"),
                                  "to": data[off:off + 1].decode("latin-1")}
                rec["field"] = field_at(lineage, off)
        return rec

    def _signature_ok(self, head: bytes, sig: bytes) -> bool:
        try:
            self.key.public_key().verify(sig, head)
            return True
        except InvalidSignature:
            return False

    def verify_all(self) -> dict:
        t0 = time.perf_counter()
        failed_records, failed_batches = [], []
        mismatched = {w.name: [] for w in self.witnesses}
        prev_head, checked = ZERO, 0
        batches = self.repo.batches()
        for b in batches:
            bid = b["batch_id"]
            rows = {r["seq"]: r for r in self.repo.raw_in_batch(b)}
            leaves, leaf_bad = [], False
            for rec, data in self.store.iter_seq_range(b["first_seq"], b["last_seq"]):
                stored = rows[rec.seq]["raw_sha256"]
                if hashlib.sha256(data).hexdigest() != stored:
                    leaf_bad = True
                    failed_records.append(self._failed_record(rec.raw_id, rec.seq, bid, data))
                leaves.append(leaf_hash(bytes.fromhex(stored), rec.seq))
                checked += 1
            if leaf_bad:
                failed_batches.append({"batch_id": bid, "reason": "leaf_mismatch"})
            root = mth(leaves)
            if root.hex() != b["merkle_root"]:
                failed_batches.append({"batch_id": bid, "reason": "root_mismatch"})
            head = bytes.fromhex(b["head"])
            if make_head(bid, bytes.fromhex(b["merkle_root"]), bytes.fromhex(b["prev_head"])) != head \
                    or bytes.fromhex(b["prev_head"]) != prev_head:
                failed_batches.append({"batch_id": bid, "reason": "chain_break"})
            if not self._signature_ok(head, bytes.fromhex(b["signature"])):
                failed_batches.append({"batch_id": bid, "reason": "bad_signature"})
            for w in self.witnesses:
                if w.head_for(bid) != head:
                    mismatched[w.name].append(bid)
            prev_head = head
        if failed_records or failed_batches:
            verdict = "tampered"
        elif any(mismatched.values()):
            verdict = "witness_mismatch"
        else:
            verdict = "verified"
        result = dict(verdict=verdict, checked_records=checked, checked_batches=len(batches),
                      took_ms=round((time.perf_counter() - t0) * 1000), failed_records=failed_records,
                      failed_batches=failed_batches,
                      witness_status=[{"name": n, "agree": not m, "mismatched_batches": m} for n, m in mismatched.items()],
                      pending_seal=len(self.unsealed))
        self.repo.set_meta("last_verify", {**result, "at": _wall_ms()})
        self.publish("verify.completed", {k: result[k] for k in ("verdict", "failed_records", "witness_status")})
        return result

    # ---- single-record proof (§8.6) -------------------------------------------------------------------------------
    def verify_record(self, raw_id: str) -> dict | None:
        """None if the record isn't sealed yet. Raises KeyError for an unknown raw_id."""
        rec = self.repo.get_raw(raw_id)
        if rec is None:
            raise KeyError(raw_id)
        if rec.batch_id is None:
            return None
        b = self.repo.batch(rec.batch_id)
        data = self.store.read(raw_id)
        sha_now = hashlib.sha256(data).hexdigest()
        rows = self.repo.raw_in_batch(b)
        m = rec.seq - b["first_seq"]
        leaves = [leaf_hash(bytes.fromhex(r["raw_sha256"]), r["seq"]) for r in rows]
        leaves[m] = leaf_hash(bytes.fromhex(sha_now), rec.seq)
        path = audit_path(leaves, m)
        root_ok = root_from_path(leaves[m], m, len(leaves), path).hex() == b["merkle_root"]
        head = bytes.fromhex(b["head"])
        signature_ok = self._signature_ok(head, bytes.fromhex(b["signature"])) and \
            make_head(b["batch_id"], bytes.fromhex(b["merkle_root"]), bytes.fromhex(b["prev_head"])) == head
        witnesses = [{"name": w.name, "agree": w.head_for(b["batch_id"]) == head} for w in self.witnesses]
        out = dict(raw_id=raw_id, ok=False, seq=rec.seq, batch_id=b["batch_id"], leaf_index=m,
                   sha256_stored=rec.raw_sha256, sha256_now=sha_now, audit_path=[p.hex() for p in path],
                   root_ok=root_ok, signature_ok=signature_ok, witnesses=witnesses,
                   first_diff_offset=None, changed=None, field=None)
        if sha_now != rec.raw_sha256:
            fr = self._failed_record(raw_id, rec.seq, b["batch_id"], data)
            out.update(first_diff_offset=fr["first_diff_offset"], changed=fr["changed"], field=fr["field"])
        out["ok"] = sha_now == rec.raw_sha256 and root_ok and signature_ok and all(w["agree"] for w in witnesses)
        return out

    # ---- demo: tamper (§8.7) and insider re-seal (§8.8) -----------------------------------------------------------
    def tamper_target(self) -> RawRecord | None:
        r = self.repo.con.execute("SELECT raw_id FROM raw_events WHERE seq=?", (TAMPER_SEQ,)).fetchone()
        return self.repo.get_raw(r[0]) if r else None

    def reseal_from(self, batch_id: int) -> list[int]:
        """Rewrite stored hashes to match the vault, then recompute and re-sign every head from batch_id on.
        Witness stores are not touched, so they now disagree from batch_id onward."""
        batches = self.repo.batches(batch_id)
        prev_row = self.repo.batch(batch_id - 1)
        prev = bytes.fromhex(prev_row["head"]) if prev_row else ZERO
        with self.repo.tx():
            for b in batches:
                leaves = []
                for rec, data in self.store.iter_seq_range(b["first_seq"], b["last_seq"]):
                    sha = hashlib.sha256(data).hexdigest()
                    self.repo.set_raw_sha(rec.raw_id, sha)
                    leaves.append(leaf_hash(bytes.fromhex(sha), rec.seq))
                root = mth(leaves)
                head = make_head(b["batch_id"], root, prev)
                self.repo.update_batch_seal(b["batch_id"], root.hex(), prev.hex(), head.hex(), self.key.sign(head).hex())
                prev = head
        return [b["batch_id"] for b in batches]
