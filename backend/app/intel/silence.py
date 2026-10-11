"""Log-silence detection (TRD.md §11, FL-09). Uses real wall time between arrivals; `wall` is injectable for tests."""
import statistics
import time
from collections import deque


def _wall_ms() -> int:
    return int(time.time() * 1000)


class _Source:
    def __init__(self, first_wall: int):
        self.gaps: deque[float] = deque(maxlen=20)
        self.first, self.last = first_wall, first_wall
        self.monitored, self.status = False, "learning"


class SilenceMonitor:
    def __init__(self, repo, publish, min_seconds: float, wall=_wall_ms):
        self.repo, self.publish, self.min_s, self.wall = repo, publish, min_seconds, wall
        self.sources: dict[str, _Source] = {}

    def expected_gap(self, s: _Source) -> float | None:
        return round(statistics.median(s.gaps), 3) if s.gaps else None

    def threshold(self, s: _Source) -> float:
        return max(self.min_s, 5 * (self.expected_gap(s) or 0))

    def on_events(self, events) -> None:
        walls = self.repo.wall_times([e.raw_id for e in events])
        for ev in sorted(events, key=lambda e: walls.get(e.raw_id, 0)):
            dev, w = ev.anvaya.device, walls.get(ev.raw_id, self.wall())
            s = self.sources.get(dev)
            if s is None:
                self.sources[dev] = _Source(w)
                continue
            if w > s.last:
                s.gaps.append((w - s.last) / 1000)
                s.last = w
            # Monitored once it has ≥ 3 gaps and has been sending for ≥ 60 s; a one-off burst never qualifies.
            if not s.monitored and len(s.gaps) >= 3 and s.last - s.first >= 60_000:
                s.monitored = True
            want = "active" if s.monitored else "learning"
            if s.status != want:
                self._set(dev, s, want)

    def tick(self) -> None:
        now = self.wall()
        for dev, s in self.sources.items():
            if s.monitored and s.status != "silent" and (now - s.last) / 1000 > self.threshold(s):
                self._set(dev, s, "silent")

    def silent_for_s(self, dev: str) -> int:
        s = self.sources.get(dev)
        return int((self.wall() - s.last) / 1000) if s and s.status == "silent" else 0

    def _set(self, dev: str, s: _Source, status: str) -> None:
        s.status = status
        gap = self.expected_gap(s)
        self.repo.update_source_status(dev, status, gap)
        self.publish("source.status_changed", {"device": dev, "status": status, "silent_for_s": self.silent_for_s(dev),
                                               "expected_gap_s": gap})
