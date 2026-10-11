"""Envelope → flat `events` columns (BACKEND_SCHEMA.md §2.2). The same function feeds Parquet."""
import json

from app.core.models import NormalizedEvent


def _j(o) -> str:
    return json.dumps(o, separators=(",", ":"))


def flatten(ev: NormalizedEvent) -> dict:
    o, a = ev.ocsf, ev.anvaya
    net = (o.get("evidences") or [{}])[0] if o["class_uid"] == 2004 else o
    src, dst = net.get("src_endpoint") or {}, net.get("dst_endpoint") or {}
    ci = net.get("connection_info") or {}
    return {
        "event_id": ev.event_id, "raw_id": ev.raw_id, "seq": ev.seq, "time": o["time"],
        "device": a.device, "vendor": a.vendor, "product": a.product, "format": a.format,
        "class_uid": o["class_uid"], "class_name": o["class_name"], "activity_name": o["activity_name"],
        "src_ip": src.get("ip"), "src_port": src.get("port"), "dst_ip": dst.get("ip"), "dst_port": dst.get("port"),
        "protocol": ci.get("protocol_name"), "direction": ci.get("direction"),
        "user_name": (o.get("user") or {}).get("name"),
        "action": o.get("action"), "status": o.get("status"), "severity": o["severity"],
        "title": (o.get("finding_info") or {}).get("title") if o["class_uid"] == 2004 else None,
        "parse_confidence": a.parse_confidence, "parser": a.parser, "rule_id": a.rule_id,
        "roundtrip_ok": int(a.roundtrip.ok), "roundtrip_coverage": a.roundtrip.coverage,
        "ocsf_json": _j(o), "anvaya_json": _j(a.model_dump()),
    }
