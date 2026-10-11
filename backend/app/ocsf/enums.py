"""OCSF enum ids, read from the vendored schema in backend/app/ocsf/schema (TRD.md §7.3). Never hard-coded.

schema/<class>.json      JSON Schema export (validation), profiles security_control + datetime
schema/api/<name>.json   the same version's native definitions, which carry the enum captions the JSON Schema lacks
schema/VERSION           the vendored OCSF version
"""
import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).with_name("schema")
CLASS_FILES = {4001: "network_activity", 2004: "detection_finding", 3002: "authentication"}
ENUM_ATTRS = ("activity_id", "severity_id", "action_id", "disposition_id", "status_id")


class OcsfSchemaMissing(RuntimeError):
    pass


def _read(f: Path) -> dict:
    if not f.exists():
        raise OcsfSchemaMissing(f"Vendored OCSF schema missing: {f}. Export it from schema.ocsf.io (IMPLEMENTATION_PLAN.md "
                                f"§3 step 3) and run `make check-ocsf`.")
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:
        raise OcsfSchemaMissing(f"{f} is not valid JSON: {e}")


def load_class(name: str, schema_dir: Path = SCHEMA_DIR) -> dict:
    return _read(schema_dir / f"{name}.json")


def _captions(defn: dict, attr: str) -> dict[str, int]:
    enum = defn.get("attributes", {}).get(attr, {}).get("enum", {})
    return {v["caption"]: int(k) for k, v in enum.items()}


class Enums:
    def __init__(self, schema_dir: Path = SCHEMA_DIR):
        vf = schema_dir / "VERSION"
        if not vf.exists():
            raise OcsfSchemaMissing(f"Missing {vf}: write the vendored OCSF version string there.")
        self.version = vf.read_text(encoding="utf-8").strip()
        api = schema_dir / "api"
        self.tables: dict[int, dict[str, dict[str, int]]] = {}
        self.classes: dict[int, tuple[str, int, str]] = {}
        for uid, name in CLASS_FILES.items():
            defn = _read(api / f"{name}.json")
            if int(defn["uid"]) != uid:
                raise OcsfSchemaMissing(f"{api / name}.json is class {defn['uid']}, expected {uid}")
            self.classes[uid] = (defn["caption"], int(defn["category_uid"]), defn["category_name"])
            self.tables[uid] = {a: _captions(defn, a) for a in ENUM_ATTRS}
        self.direction = _captions(_read(api / "network_connection_info.json"), "direction_id")
        self.observable = _captions(_read(api / "observable.json"), "type_id")
        self.device_type = _captions(_read(api / "device.json"), "type_id")

    def class_info(self, class_uid: int) -> tuple[str, int, str]:
        return self.classes[class_uid]

    def id_for(self, class_uid: int, attr: str, caption: str) -> int:
        table = self.tables[class_uid].get(attr, {})
        if caption not in table:
            raise KeyError(f"OCSF {CLASS_FILES[class_uid]}.{attr} has no value {caption!r} in schema {self.version}")
        return table[caption]

    def direction_id(self, caption: str) -> int:
        return self.direction[caption]

    def observable_type(self, caption: str) -> int:
        return self.observable[caption]

    def device_type_id(self, caption: str) -> int:
        return self.device_type[caption]
