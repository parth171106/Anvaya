"""Syslog header pre-processing (TRD.md §6.1). Spans are [start, end) character offsets into the decoded text;
callers convert to byte offsets with ByteOffsets when the text isn't ASCII."""
import re
from dataclasses import dataclass, field

Span = tuple[int, int]

PATTERNS = [  # tried in this order; the first match wins
    ("asa3164y", re.compile(r"^<(?P<pri>\d{1,3})>(?P<ts>[A-Z][a-z]{2} \d{2} \d{4} \d{2}:\d{2}:\d{2}) (?P<host>\S+) : ")),
    ("bsd3164", re.compile(r"^<(?P<pri>\d{1,3})>(?P<ts>[A-Z][a-z]{2} [ \d]\d \d{2}:\d{2}:\d{2}) (?P<host>\S+) "
                           r"(?P<app>[\w.\-]+)\[(?P<pid>\d+)\]: ")),
    ("pri_only", re.compile(r"^<(?P<pri>\d{1,3})>")),
]


@dataclass
class HeaderSplit:
    pattern_id: str                                   # asa3164y | bsd3164 | pri_only | none
    fields: dict[str, tuple[str, Span]] = field(default_factory=dict)
    body_offset: int = 0


def split(text: str) -> HeaderSplit:
    for pid, rx in PATTERNS:
        m = rx.match(text)
        if m:
            return HeaderSplit(pid, {k: (v, m.span(k)) for k, v in m.groupdict().items()}, m.end())
    return HeaderSplit("none")


class ByteOffsets:
    """Character offset → byte offset in the UTF-8 encoding (identity for ASCII text)."""

    def __init__(self, text: str):
        self.table = None
        if not text.isascii():
            acc, self.table = 0, [0]
            for ch in text:
                acc += len(ch.encode("utf-8", "surrogateescape"))
                self.table.append(acc)

    def __call__(self, i: int) -> int:
        return i if self.table is None else self.table[i]

    def span(self, s: Span) -> Span:
        return (self(s[0]), self(s[1]))
