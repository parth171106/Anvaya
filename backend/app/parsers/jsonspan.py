"""Span-aware JSON scan (TRD.md §7.2). Records [start, end) of each scalar's content (inside the quotes for strings,
the literal for numbers/booleans/null). Keys are flattened with dots; array items use [i]."""
import json
import re

_WS = re.compile(r"[ \t\n\r]*")
_NUM = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_STR = re.compile(r'"((?:[^"\\]|\\.)*)"')


class JsonSpanError(ValueError):
    pass


def scan(text: str, pos: int = 0) -> tuple[list[tuple[str, str, object, tuple[int, int]]], int]:
    """Returns ([(path, raw_text, value, span)], end) for the JSON value starting at `pos` (after whitespace)."""
    out: list = []
    end = _value(text, _ws(text, pos), "", out)
    return out, end


def _ws(t, i):
    return _WS.match(t, i).end()


def _value(t, i, path, out):
    if i >= len(t):
        raise JsonSpanError("unexpected end")
    c = t[i]
    if c == "{":
        i = _ws(t, i + 1)
        if t.startswith("}", i):
            return i + 1
        while True:
            m = _STR.match(t, i)
            if not m:
                raise JsonSpanError(f"expected key at {i}")
            key = json.loads(m.group(0))
            i = _ws(t, m.end())
            if not t.startswith(":", i):
                raise JsonSpanError(f"expected ':' at {i}")
            i = _value(t, _ws(t, i + 1), f"{path}.{key}" if path else key, out)
            i = _ws(t, i)
            if t.startswith(",", i):
                i = _ws(t, i + 1)
            elif t.startswith("}", i):
                return i + 1
            else:
                raise JsonSpanError(f"expected ',' or '}}' at {i}")
    if c == "[":
        i, n = _ws(t, i + 1), 0
        if t.startswith("]", i):
            return i + 1
        while True:
            i = _ws(t, _value(t, i, f"{path}[{n}]", out))
            n += 1
            if t.startswith(",", i):
                i = _ws(t, i + 1)
            elif t.startswith("]", i):
                return i + 1
            else:
                raise JsonSpanError(f"expected ',' or ']' at {i}")
    if c == '"':
        m = _STR.match(t, i)
        if not m:
            raise JsonSpanError(f"bad string at {i}")
        out.append((path, m.group(1), json.loads(m.group(0)), m.span(1)))
        return m.end()
    for lit, val in (("true", True), ("false", False), ("null", None)):
        if t.startswith(lit, i):
            out.append((path, lit, val, (i, i + len(lit))))
            return i + len(lit)
    m = _NUM.match(t, i)
    if not m:
        raise JsonSpanError(f"unexpected character at {i}")
    out.append((path, m.group(0), json.loads(m.group(0)), m.span()))
    return m.end()
