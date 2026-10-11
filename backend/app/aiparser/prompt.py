"""The parser-drafting prompt (BACKEND_SCHEMA.md §4.5)."""
from app.parsers.registry import BUILTIN_DIR

TEMPLATE = """You write ANVAYA parser packs in YAML. Output ONLY the YAML document, no prose, no fences.

Pack format (follow it exactly):
{CISCO_ASA_PACK}

Allowed OCSF targets: time, metadata.original_time, device.hostname, action, connection_info.protocol_name,
src_endpoint.ip, src_endpoint.port, dst_endpoint.ip, dst_endpoint.port, traffic.bytes, user.name, status,
unmapped.<name>.
Allowed extractor types: regex, json, kv, delimited. Allowed transforms: lower, upper, enum, timestamp, kv_value.
Rules:
- Every field present in the lines must be mapped to a target or to unmapped.<name>. Drop nothing.
- Name the pack after the vendor marker you see; version 1.0.0; origin ai_draft; priority 40.
- Use class_uid 4001 for network sessions. Use activity Traffic for allowed sessions and Refuse for denied ones.
- Device timestamps without an offset use source_timezone Asia/Kolkata.

Sample lines (14):
{TRAIN_LINES}"""


def drafting_prompt(train_lines: list[str]) -> str:
    asa = (BUILTIN_DIR / "cisco-asa.yaml").read_text(encoding="utf-8").rstrip("\n")
    return TEMPLATE.replace("{CISCO_ASA_PACK}", asa).replace("{TRAIN_LINES}", "\n".join(train_lines))
