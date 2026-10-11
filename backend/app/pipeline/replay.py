"""Replay: re-queue raw_ids through the current packs; the vault and ledger are untouched (FL-08 step 6)."""
from app.core.ids import seq_id


class ReplayManager:
    def __init__(self, queue, publish):
        self.queue, self.publish = queue, publish
        self.reset()

    def reset(self) -> None:
        self.n = 0
        self.active: dict[str, dict] = {}
        self.pending: dict[str, str] = {}      # raw_id → replay_id

    def start(self, raw_ids: list[str]) -> tuple[str, int]:
        self.n += 1
        rp = seq_id("rp", self.n)
        self.active[rp] = {"total": len(raw_ids), "done": 0, "parsed": 0}
        for rid in raw_ids:
            self.pending[rid] = rp
            self.queue.put_nowait(rid)
        return rp, len(raw_ids)

    def on_processed(self, raw_id: str, parsed: bool) -> None:
        rp = self.pending.pop(raw_id, None)
        if rp is None:
            return
        st = self.active[rp]
        st["done"] += 1
        st["parsed"] += parsed
        self.publish("replay.progress", {"replay_id": rp, "done": st["done"], "total": st["total"]})
        if st["done"] == st["total"]:
            self.publish("replay.completed", {"replay_id": rp, "parsed": st["parsed"],
                                              "still_quarantined": st["total"] - st["parsed"]})
            del self.active[rp]
