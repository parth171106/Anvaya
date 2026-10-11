"""ParseResult → OCSF object + lineage (TRD.md §7.2–§7.3)."""
import ipaddress
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.ocsf.lineage import Trace
from app.parsers.engine import ParseResult, _text
from app.parsers.extractors import Extracted

LOG_NAMES = {"cisco-asa-syslog": "syslog", "suricata-eve-json": "eve-json", "fortigate-kv": "fortigate-kv",
             "acme-edge-pipe": "edge-pipe"}
CONSTANTS = ("activity", "action", "disposition", "severity", "status")
_PATH = re.compile(r"([^.\[\]]+)(?:\[(\d+)\])?")


class MappingError(ValueError):
    pass


def set_path(obj: dict, path: str, value) -> None:
    """Set a dotted path with optional [i] list indexes, e.g. evidences[0].src_endpoint.ip."""
    parts = path.split(".")
    for i, part in enumerate(parts):
        name, idx = _PATH.fullmatch(part).groups()
        last = i == len(parts) - 1
        if idx is None:
            if last:
                obj[name] = value
            else:
                obj = obj.setdefault(name, {})
        else:
            lst = obj.setdefault(name, [])
            k = int(idx)
            while len(lst) <= k:
                lst.append({})
            if last:
                lst[k] = value
            else:
                obj = lst[k]


def get_path(obj, path: str):
    for part in path.split("."):
        name, idx = _PATH.fullmatch(part).groups()
        if not isinstance(obj, dict) or name not in obj:
            return None
        obj = obj[name]
        if idx is not None:
            if not isinstance(obj, list) or int(idx) >= len(obj):
                return None
            obj = obj[int(idx)]
    return obj


def to_epoch_ms(text: str, fmt: str, tz: str) -> int:
    dt = datetime.strptime(text, fmt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return int(dt.timestamp() * 1000)


def iso_z(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, timezone.utc)
    frac = f".{ms % 1000:03d}" if ms % 1000 else ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + frac + "Z"


class Mapped:
    """Result of mapping one record."""

    def __init__(self):
        self.ocsf: dict = {}
        self.traces: list[Trace] = []
        self.typed_total = self.typed_ok = 0
        self.mapped_names: set[str] = set()     # extracted values feeding a non-unmapped path
        self.ip_paths: list[str] = []
        self.original_time: str | None = None


def map_to_ocsf(res: ParseResult, text: str, event_id: str, enums) -> Mapped:
    pack, rule = res.pack, res.rule
    by_name: dict[str, Extracted] = {v.name: v for v in res.values}
    out = Mapped()
    unmapped: dict = {}
    consumed: set[str] = set()

    def apply(key: str, m: dict) -> None:
        names = key.split("+")
        vals = [by_name[n] for n in names if n in by_name]
        if len(vals) != len(names):
            return  # a source field absent from this record: nothing to map (counts against `required`)
        consumed.update(names)
        texts = [v.text for v in vals]
        spans = [v.span for v in vals]
        joined = " ".join(_text(v) for v in vals)
        value, derived = joined, len(vals) > 1
        t = m.get("transform")
        tname = t if isinstance(t, str) else (next(iter(t)) if t else None)
        if tname == "kv_value":
            v = vals[0]
            i = v.text.find("=")
            if i < 0:
                raise MappingError(f"{key}: no '=' in {v.text!r}")
            value, texts, spans = v.text[i + 1:], [v.text[i + 1:]], [(v.span[0] + i + 1, v.span[1])]
        elif tname in ("lower", "upper"):
            value, derived = (joined.lower() if tname == "lower" else joined.upper()), True
        elif tname == "enum":
            table = {str(k): v for k, v in t["enum"].items()}
            if joined not in table:
                raise MappingError(f"{key}: {joined!r} not in enum")
            value, derived = table[joined], True
        elif tname == "timestamp":
            try:
                value = to_epoch_ms(joined, t["timestamp"], pack.source_timezone)
            except ValueError as e:
                raise MappingError(f"{key}: {e}")
            derived = True
        typ = m.get("type")
        if typ in ("int", "ip"):
            out.typed_total += 1
            try:
                value = int(value) if typ == "int" else str(ipaddress.ip_address(value))
                out.typed_ok += 1
            except ValueError:
                pass
        to = m["to"]
        if to.startswith("unmapped."):
            set_path(unmapped, to[len("unmapped."):], value if isinstance(value, str) else str(value))
        else:
            set_path(out.ocsf, to, value)
            out.mapped_names.update(names)
            if typ == "ip":
                out.ip_paths.append(to)
        out.traces.append(Trace(to, spans, derived, texts, names))
        if m.get("also"):
            if m["also"] == "metadata.original_time":
                out.original_time = joined
            set_path(out.ocsf, m["also"], joined)
            out.traces.append(Trace(m["also"], [v.span for v in vals], len(vals) > 1, [v.text for v in vals], names))

    for name, m in pack.header_fields.items():
        apply(name, m)
    for name, m in pack.prefix_fields.items():
        apply(name, m)
    for key, m in rule.map.items():
        apply(key, m)
    for v in res.values:  # nothing extracted is dropped: anything not mapped lands in unmapped
        if v.name not in consumed:
            apply(v.name, {"to": f"unmapped.{v.name}"})

    # Rule constants: values from the pack, lineage → the span of the field that selected the rule.
    cls = int(rule.ocsf["class_uid"])
    mapped_paths = {t.path for t in out.traces}
    for c in CONSTANTS:
        if c not in rule.ocsf:
            continue
        path = "activity_name" if c == "activity" else c
        if get_path(out.ocsf, path) is None:
            out.ocsf[path] = rule.ocsf[c]
        if path not in mapped_paths and res.selector is not None:
            out.traces.append(Trace(path, [res.selector.span], True, [res.selector.text], [res.selector.name]))

    o = out.ocsf
    class_name, category_uid, category_name = enums.class_info(cls)
    activity = o.pop("activity_name", None)
    if activity is None:
        raise MappingError("rule has no activity")
    head = {"class_uid": cls, "class_name": class_name, "category_uid": category_uid, "category_name": category_name,
            "activity_id": enums.id_for(cls, "activity_id", activity), "activity_name": activity}
    head["type_uid"] = cls * 100 + head["activity_id"]
    head["type_name"] = f"{class_name}: {activity}"
    sev = o.pop("severity", "Informational")
    head["severity_id"], head["severity"] = enums.id_for(cls, "severity_id", sev), sev
    for attr in ("action", "disposition", "status"):
        if attr in o:
            val = o.pop(attr)
            head[f"{attr}_id"], head[attr] = enums.id_for(cls, f"{attr}_id", val), val
    # OCSF 1.9 requires connection_info.direction_id; sources that don't state a direction get "Unknown".
    for ci in [o.get("connection_info")] + [ev.get("connection_info") for ev in o.get("evidences", [])]:
        if isinstance(ci, dict):
            ci["direction_id"] = enums.direction_id(ci.get("direction", "Unknown"))
    if pack.spec.get("device_type"):  # OCSF requires device.type_id; the pack names the device type
        dev = o.setdefault("device", {})
        dev["type_id"], dev["type"] = enums.device_type_id(pack.spec["device_type"]), pack.spec["device_type"]
    out.ocsf = head | o
    o = out.ocsf
    if "time" not in o:
        raise MappingError("no time")
    o["time_dt"] = iso_z(o["time"])
    meta = o.setdefault("metadata", {})
    out.ocsf["metadata"] = {"version": enums.version, "uid": event_id, "log_name": LOG_NAMES.get(pack.format, pack.format),
                            **meta, "product": {"vendor_name": pack.vendor, "name": pack.product}}
    obs = []
    ip_type, user_type = enums.observable_type("IP Address"), enums.observable_type("User Name")
    for t in sorted((t for t in out.traces if not t.path.startswith("unmapped.")), key=lambda t: t.spans[0][0]):
        if t.path in out.ip_paths and get_path(o, t.path) is not None:
            obs.append({"name": t.path, "type_id": ip_type, "type": "IP Address", "value": get_path(o, t.path)})
        elif t.path == "user.name":
            obs.append({"name": t.path, "type_id": user_type, "type": "User Name", "value": get_path(o, t.path)})
    if obs:
        o["observables"] = obs
    o["raw_data"] = text
    o["unmapped"] = unmapped
    return out
