"""Shape signature for quarantine grouping (TRD.md §6.3)."""
from app.parsers import syslog_header

DELIMS = {"|": "pipe", ",": "comma", "\t": "tab", ";": "semicolon", " ": "space"}


def shape(text: str) -> tuple[str, str, int, str]:
    """→ (signature, delimiter, field_count, first_token), e.g. ('EDGE|x12', '|', 12, 'EDGE')."""
    body = text[syslog_header.split(text).body_offset:]
    delim = max(DELIMS, key=body.count)  # ties keep the order above
    fields = body.split(delim)
    return f"{fields[0]}{delim}x{len(fields)}", delim, len(fields), fields[0]


def shape_label(signature_parts: tuple[str, str, int, str], count: int) -> str:
    _, delim, n, first = signature_parts
    return f"{count} records · {n} {DELIMS[delim]}-delimited fields starting with {first}"
