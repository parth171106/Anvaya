"""Round-trip losslessness check (TRD.md §7.5)."""
from app.ocsf.lineage import Trace

Span = tuple[int, int]


def coverage(accounted: list[Span], total: int) -> float:
    covered, end = 0, 0
    for s, t in sorted(accounted):
        s, t = max(s, end), min(t, total)
        if t > s:
            covered += t - s
            end = t
    return round(covered / total, 4) if total else 1.0


def check_roundtrip(raw: bytes, encoding: str, traces: list[Trace], accounted: list[Span],
                    extracted_names: list[str]) -> dict:
    enc = "utf-8" if encoding == "utf-8" else "latin-1"

    def at(span):
        return raw[span[0]:span[1]].decode(enc, "replace")

    value_check = True
    for t in traces:
        if not t.derived:
            value_check &= len(t.spans) == len(t.texts) and all(at(s) == x for s, x in zip(t.spans, t.texts))
        else:
            value_check &= all(x in at(s) for s, x in zip(t.spans, t.texts))
    total = len(raw) - (1 if raw.endswith(b"\n") else 0)
    cov = coverage(accounted, total)
    used = {s for t in traces for s in t.sources}
    dropped = sum(1 for n in extracted_names if n not in used)
    return {"ok": bool(value_check and cov >= 0.95 and dropped == 0), "value_check": bool(value_check),
            "coverage": cov, "dropped": dropped}
