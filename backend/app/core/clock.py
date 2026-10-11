"""WallClock and ScenarioClock (TRD.md §9)."""
import asyncio
import time
from datetime import datetime

from generator.formats import IST, at


def wall_ms() -> int:
    return int(time.time() * 1000)


class WallClock:
    phase = "idle"

    def now_ms(self) -> int:
        return wall_ms()

    def label(self) -> str:
        return "Local time"

    async def sleep_until(self, ms: int) -> None:
        while (d := ms - self.now_ms()) > 0:
            await asyncio.sleep(min(d / 1000, 0.2))


class ScenarioClock:
    """now = anchor_scn + (wall − anchor_wall) × speed. Scripted phase runs from 10:00:00 at `speed`; at 10:12:00 it
    re-anchors to 1× (steady). Speed changes re-anchor without a time jump."""

    def __init__(self, speed: int = 20):
        self.speed = speed          # selected playback speed (10 | 20 | 40)
        self.on_change = None       # called with no args when the phase changes on its own (scripted → steady)
        self.reset()

    def reset(self) -> None:
        self.phase, self.rate = "idle", 1
        self.anchor_wall = self.anchor_scn = self.steady_ms = 0

    def start(self, d=None, speed: int | None = None) -> None:
        d = d or datetime.now(IST).date()
        self.speed = speed or self.speed
        self.anchor_wall, self.anchor_scn, self.rate = wall_ms(), at(d, 10, 0), self.speed
        self.steady_ms, self.phase = at(d, 10, 12), "scripted"

    def set_speed(self, speed: int) -> None:
        self.speed = speed
        if self.phase == "scripted":
            now = self.now_ms()
            self.anchor_wall, self.anchor_scn, self.rate = wall_ms(), now, speed

    def _now(self, wall: float) -> float:
        return self.anchor_scn + (wall - self.anchor_wall) * self.rate

    def now_ms(self) -> int:
        if self.phase == "idle":
            return wall_ms()
        wall = wall_ms()
        if self.phase == "scripted" and self._now(wall) >= self.steady_ms:
            cross = self.anchor_wall + (self.steady_ms - self.anchor_scn) / self.rate
            self.anchor_wall, self.anchor_scn, self.rate, self.phase = cross, self.steady_ms, 1, "steady"
            if self.on_change:
                self.on_change()
        return int(self._now(wall))

    def label(self) -> str:
        return "Scenario clock"

    def wall_delay_s(self, ms: int) -> float:
        """Real seconds until scenario time `ms`, accounting for the drop to 1× at 10:12:00."""
        now = self.now_ms()
        if ms <= now:
            return 0.0
        if self.phase == "scripted" and ms > self.steady_ms:
            return ((self.steady_ms - now) / self.rate + (ms - self.steady_ms)) / 1000
        return (ms - now) / self.rate / 1000

    async def sleep_until(self, ms: int) -> None:
        while (d := self.wall_delay_s(ms)) > 0:
            await asyncio.sleep(min(d, 0.2))  # short slices so a speed change takes effect promptly
