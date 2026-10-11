"""Lineage entries: build, order, convert to byte spans, look up by offset."""
from dataclasses import dataclass, field

Span = tuple[int, int]


@dataclass
class Trace:
    """One lineage entry plus what the round-trip check needs (the source token texts)."""
    path: str
    spans: list[Span]
    derived: bool
    texts: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)   # extracted value names this entry consumes

    def public(self) -> dict:
        return {"path": self.path, "spans": [list(s) for s in self.spans], "derived": self.derived}


def ordered(traces: list[Trace]) -> list[Trace]:
    """OCSF fields first, then unmapped; each group by first span start (stable)."""
    key = lambda t: (t.path.startswith("unmapped."), t.spans[0][0] if t.spans else 0)
    return sorted(traces, key=key)


def to_bytes(traces: list[Trace], offsets) -> list[Trace]:
    for t in traces:
        t.spans = [offsets.span(s) for s in t.spans]
    return traces


def field_at(lineage: list[dict], offset: int) -> str | None:
    """Path of the narrowest lineage span containing `offset`."""
    best = None
    for e in lineage:
        for s, t in e["spans"]:
            if s <= offset < t and (best is None or t - s < best[0]):
                best = (t - s, e["path"])
    return best[1] if best else None
