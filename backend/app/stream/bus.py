"""In-process pub/sub with monotonic ids and a 2,000-message replay buffer (TRD.md API 27)."""
import asyncio
from collections import deque

BUFFER = 2000


class EventBus:
    def __init__(self):
        self.next_id = 1                     # keeps increasing across demo resets
        self.buffer: deque = deque(maxlen=BUFFER)
        self.subscribers: set[asyncio.Queue] = set()

    def publish(self, event: str, data) -> None:
        msg = (self.next_id, event, data)
        self.next_id += 1
        self.buffer.append(msg)
        for q in list(self.subscribers):
            q.put_nowait(msg)

    def clear(self) -> None:
        self.buffer.clear()

    def subscribe(self, last_id: int | None = None) -> tuple[asyncio.Queue, list | None]:
        """→ (queue of new messages, backlog to replay first). backlog is None when last_id is older than the buffer
        (the caller sends `resync`)."""
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(q)
        if last_id is None:
            return q, []
        if self.buffer and last_id < self.buffer[0][0] - 1:
            return q, None
        return q, [m for m in self.buffer if m[0] > last_id]

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)
