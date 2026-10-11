"""Extractors (TRD.md §7.2). Each returns (values, accounted_spans); every value carries its span in the text."""
import re
from dataclasses import dataclass

import regex

from app.parsers import jsonspan

Span = tuple[int, int]
REGEX_TIMEOUT_S = 0.05


class ExtractError(ValueError):
    pass


@dataclass
class Extracted:
    name: str
    text: str                    # exactly the source characters at `span`
    span: Span
    from_header: bool = False
    value: object = None         # decoded value (JSON); None → use text


def run_regex(rx: regex.Pattern, text: str, pos: int) -> tuple[list[Extracted], list[Span]]:
    """Match at `pos` (on the slice, so a leading ^ anchors there); spans are offsets into `text`."""
    try:
        m = rx.match(text[pos:], timeout=REGEX_TIMEOUT_S)
    except TimeoutError:
        raise ExtractError("regex timeout")
    if not m:
        raise ExtractError("regex did not match")
    vals = [Extracted(n, m.group(n), (m.start(n) + pos, m.end(n) + pos)) for n in rx.groupindex if m.group(n) is not None]
    return vals, [(m.start() + pos, m.end() + pos)]


def json_extract(text: str, pos: int) -> tuple[list[Extracted], list[Span]]:
    try:
        values, end = jsonspan.scan(text, pos)
    except jsonspan.JsonSpanError as e:
        raise ExtractError(f"json: {e}")
    start = pos + (len(text[pos:]) - len(text[pos:].lstrip()))
    return [Extracted(p, raw, span, value=val) for p, raw, val, span in values], [(start, end)]


_KV = re.compile(r'([A-Za-z_][\w.-]*)=(?:"([^"]*)"|(\S*))')


def kv_extract(text: str, pos: int) -> tuple[list[Extracted], list[Span]]:
    out, i, end = [], pos, pos
    while i < len(text):
        m = _KV.match(text, i)
        if not m:
            break
        g = 2 if m.group(2) is not None else 3
        out.append(Extracted(m.group(1), m.group(g), m.span(g)))
        end = m.end()
        i = end + len(text[end:]) - len(text[end:].lstrip(" \t"))
    if not out:
        raise ExtractError("kv: no key=value tokens")
    return out, [(pos, end)]  # tokens and the whitespace between them


def delimited_extract(text: str, pos: int, delimiter: str, columns: list[str]) -> tuple[list[Extracted], list[Span]]:
    cells = text[pos:].split(delimiter)
    if len(cells) != len(columns):
        raise ExtractError(f"delimited: expected {len(columns)} fields, got {len(cells)}")
    out, i = [], pos
    for name, cell in zip(columns, cells):
        out.append(Extracted(name, cell, (i, i + len(cell))))
        i += len(cell) + len(delimiter)
    return out, [(pos, len(text))]
