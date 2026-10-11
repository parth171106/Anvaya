"""Input vetting (PRD.md EP-02). Flags only; the bytes are never modified."""
import re

MAX_PARSE_BYTES = 65536
_CONTROL = re.compile(rb"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]")  # C0 controls except NUL, TAB, LF, CR (flagged separately)


def vet(data: bytes) -> tuple[list[str], str]:
    flags = []
    if len(data) > MAX_PARSE_BYTES:
        flags.append("oversized")
    if b"\n" in data or b"\r" in data:
        flags.append("embedded_newline")
    if b"\x00" in data:
        flags.append("nul_byte")
    if _CONTROL.search(data):
        flags.append("control_chars")
    try:
        data.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        flags.append("invalid_utf8")
        encoding = "binary"
    return flags, encoding
