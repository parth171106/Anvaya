"""Rule selection and extraction for a detected pack (FL-01 step 10)."""
from dataclasses import dataclass

from app.parsers.extractors import Extracted, ExtractError, delimited_extract, json_extract, kv_extract, run_regex
from app.parsers.registry import Pack, Rule
from app.parsers.syslog_header import HeaderSplit

Span = tuple[int, int]
FIELD_CONDITIONS = ("json_equals", "kv_equals", "column_equals")


class ParseFailure(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


@dataclass
class ParseResult:
    pack: Pack
    rule: Rule
    values: list[Extracted]          # header, prefix, then body values, in order
    accounted: list[Span]            # spans consumed by successful matches (for round-trip coverage)
    selector: Extracted | None       # the field that selected the rule (lineage for rule constants)


def _text(e: Extracted) -> str:
    return str(e.value) if e.value is not None and not isinstance(e.value, bool) else e.text


def _when_matches(when: dict, by_name: dict, body: str) -> tuple[bool, str | None]:
    selector = None
    for key, expected in when.items():
        if key == "body_contains":
            if expected not in body:
                return False, None
        elif key in FIELD_CONDITIONS:
            for name, val in expected.items():
                if name not in by_name or _text(by_name[name]) != str(val):
                    return False, None
                selector = name
        else:
            if key not in by_name or _text(by_name[key]) != str(expected):
                return False, None
            selector = key
    return True, selector


def parse_with_pack(pack: Pack, text: str, hs: HeaderSplit) -> ParseResult:
    values = [Extracted(k, v, span, from_header=True) for k, (v, span) in hs.fields.items()]
    accounted = [(0, hs.body_offset)] if hs.body_offset else []
    pos = hs.body_offset
    if pack.prefix_rx:
        try:
            pv, (pspan,) = run_regex(pack.prefix_rx, text, pos)
        except ExtractError as e:
            raise ParseFailure("parse_error", f"prefix: {e}")
        values += pv
        accounted.append(pspan)
        pos = pspan[1]
    ex = pack.extractor
    try:
        if ex["type"] == "json":
            body_values, spans = json_extract(text, pos)
        elif ex["type"] == "kv":
            body_values, spans = kv_extract(text, pos)
        elif ex["type"] == "delimited":
            body_values, spans = delimited_extract(text, pos, ex["delimiter"], ex["columns"])
        else:
            body_values, spans = [], []
    except ExtractError as e:
        raise ParseFailure("parse_error", str(e))
    values += body_values
    accounted += spans
    by_name = {v.name: v for v in values}
    body = text[hs.body_offset:]
    for rule in pack.rules:
        ok, selector = _when_matches(rule.when, by_name, body)
        if ok:
            break
    else:
        raise ParseFailure("no_rule", f"no rule in {pack.id} matches")
    if rule.regex is not None:
        try:
            rv, spans = run_regex(rule.regex, text, pos)
        except ExtractError as e:
            raise ParseFailure("parse_error", f"{rule.id}: {e}")
        values += rv
        accounted += spans
    return ParseResult(pack, rule, values, accounted, by_name.get(selector) if selector else None)
