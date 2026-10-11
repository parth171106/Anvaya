"""SIEM forwarder (SIM): one RFC 5424 line with a JSON OCSF payload per normalized event, to a file sink."""
import json
from pathlib import Path


class FileSink:
    """Appends lines to one file, kept open; flushed after each batch."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._f = None

    def send(self, payload_line: str) -> None:
        if self._f is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._f = open(self.path, "a", encoding="utf-8")
        self._f.write(payload_line + "\n")

    def flush(self) -> None:
        if self._f:
            self._f.flush()

    def close(self) -> None:
        if self._f:
            self._f.close()
            self._f = None


def rfc5424(ocsf: dict) -> str:
    return f"<134>1 {ocsf['time_dt']} anvaya - ocsf - {json.dumps(ocsf, separators=(',', ':'), ensure_ascii=False)}"


class SiemForwarder:
    def __init__(self, sink, clock):
        self.sink, self.clock = sink, clock
        self.forwarded, self.last_forwarded, self.last_payload, self.error = 0, None, None, None

    def on_batch(self, events) -> None:
        lines = [rfc5424(ev.ocsf) for ev in events]
        try:
            for ln in lines:
                self.sink.send(ln)
            self.sink.flush()
            self.error = None
        except OSError as e:
            self.error = str(e)
            raise
        self.forwarded += len(lines)
        self.last_forwarded, self.last_payload = self.clock.now_ms(), lines[-1]

    def status(self) -> dict:
        return {"mode": "file_sink", "target": self.sink.path.as_posix(), "forwarded": self.forwarded,
                "last_forwarded": self.last_forwarded, "last_payload": self.last_payload,
                "status": "error" if self.error else "ok"}
