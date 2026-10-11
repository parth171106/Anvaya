from types import SimpleNamespace

from app.intel.silence import SilenceMonitor


class FakeRepo:
    def __init__(self):
        self.walls, self.status = {}, {}

    def wall_times(self, raw_ids):
        return {r: self.walls[r] for r in raw_ids}

    def update_source_status(self, device, status, gap):
        self.status[device] = (status, gap)


class Rig:
    def __init__(self):
        self.now, self.n, self.seen = 1_000_000, 0, []
        self.repo = FakeRepo()
        self.m = SilenceMonitor(self.repo, lambda e, d: self.seen.append(d), 15, wall=lambda: self.now)

    def send(self, device):
        self.n += 1
        rid = f"r-{self.n}"
        self.repo.walls[rid] = self.now
        self.m.on_events([SimpleNamespace(raw_id=rid, anvaya=SimpleNamespace(device=device))])

    def run(self, seconds, every, device):
        for _ in range(int(seconds / every)):
            self.now += int(every * 1000)
            self.send(device)
            self.m.tick()


def test_fw01_silent_after_15s_and_recovers():
    r = Rig()
    r.send("fw01")
    r.run(70, 1, "fw01")                                   # steady 1 s cadence for > 60 s → monitored, active
    assert r.repo.status["fw01"] == ("active", 1.0)
    silenced_at = r.now
    while r.repo.status["fw01"][0] != "silent":
        r.now += 1000
        r.m.tick()
    assert 15_000 < r.now - silenced_at <= 16_000            # threshold max(15, 5 × 1) = 15 s
    assert r.seen[-1] == {"device": "fw01", "status": "silent", "silent_for_s": 16, "expected_gap_s": 1.0}
    r.now += 1000
    r.send("fw01")
    assert r.repo.status["fw01"][0] == "active" and r.seen[-1]["status"] == "active"


def test_4s_sources_use_20s_threshold():
    r = Rig()
    r.send("ids01")
    r.run(80, 4, "ids01")
    last = r.now
    for _ in range(20):
        r.now += 1000
        r.m.tick()
    assert r.repo.status["ids01"][0] == "active"           # 20 s is not > 20 s
    r.now += 1000
    r.m.tick()
    assert r.repo.status["ids01"][0] == "silent" and r.now - last == 21_000


def test_br01_burst_never_monitored():
    r = Rig()
    for _ in range(20):
        r.send("br01")
        r.now += 10
    for _ in range(600):
        r.now += 1000
        r.m.tick()
    assert r.repo.status.get("br01") is None and not r.m.sources["br01"].monitored
