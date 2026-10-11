"""Parser packs: load (yaml.safe_load), validate, detect by priority (TRD.md §6.2, §7.1), hot-reload."""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import regex
import yaml

BUILTIN_DIR = Path(__file__).with_name("packs")
EXTRACTORS = {"regex", "json", "kv", "delimited"}
TRANSFORMS = {"lower", "upper", "enum", "timestamp", "kv_value"}
TYPES = {"int", "ip", "str"}


class PackError(ValueError):
    pass


@dataclass
class Rule:
    id: str
    when: dict
    regex: regex.Pattern | None
    ocsf: dict
    map: dict


class Pack:
    def __init__(self, yaml_text: str):
        try:
            spec = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise PackError(f"YAML: {e}")
        if not isinstance(spec, dict):
            raise PackError("pack must be a mapping")
        for k in ("name", "version", "priority", "vendor", "product", "format", "detect", "rules", "required"):
            if k not in spec:
                raise PackError(f"missing key: {k}")
        self.spec, self.yaml = spec, yaml_text
        self.yaml_sha256 = hashlib.sha256(yaml_text.encode()).hexdigest()
        self.name, self.version = str(spec["name"]), str(spec["version"])
        self.priority, self.origin = int(spec["priority"]), spec.get("origin", "user")
        self.vendor, self.product, self.format = spec["vendor"], spec["product"], spec["format"]
        self.source_timezone = spec.get("source_timezone", "Asia/Kolkata")
        self.detect = spec["detect"]
        self.header_fields = spec.get("header_fields") or {}
        self.required = list(spec["required"])
        self.extractor = spec.get("extractor") or {"type": "regex"}
        if self.extractor.get("type") not in EXTRACTORS:
            raise PackError(f"unknown extractor: {self.extractor.get('type')}")
        prefix = spec.get("prefix")
        self.prefix_rx = self._compile(prefix["regex"]) if prefix else None
        self.prefix_fields = prefix.get("fields", {}) if prefix else {}
        self.rules = []
        for r in spec["rules"]:
            for m in (r.get("map") or {}).values():
                self._check_mapping(r.get("id"), m)
            if self.extractor["type"] == "regex" and not r.get("regex"):
                raise PackError(f"rule {r.get('id')}: regex extractor needs a rule regex")
            self.rules.append(Rule(r["id"], r.get("when") or {}, self._compile(r["regex"]) if r.get("regex") else None,
                                   r.get("ocsf") or {}, r.get("map") or {}))
        for m in list(self.header_fields.values()) + list(self.prefix_fields.values()):
            self._check_mapping("header", m)
        self._body_rx = re.compile(self.detect["body_regex"]) if self.detect.get("body_regex") else None

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    @staticmethod
    def _compile(p: str) -> regex.Pattern:
        try:
            return regex.compile(p)
        except regex.error as e:
            raise PackError(f"bad regex {p!r}: {e}")

    @staticmethod
    def _check_mapping(where, m) -> None:
        if not isinstance(m, dict) or "to" not in m:
            raise PackError(f"{where}: every mapping needs 'to'")
        if m.get("type", "str") not in TYPES:
            raise PackError(f"{where}: unknown type {m.get('type')}")
        t = m.get("transform")
        name = t if isinstance(t, str) else (next(iter(t)) if isinstance(t, dict) and t else None)
        if t is not None and name not in TRANSFORMS:
            raise PackError(f"{where}: unknown transform {t}")

    def detects(self, hs, text: str) -> bool:
        d = self.detect
        if d.get("header", "none") != hs.pattern_id:
            return False
        if "header_app" in d and hs.fields.get("app", ("",))[0] != d["header_app"]:
            return False
        body = text[hs.body_offset:]
        if "body_json_has" in d:
            if not body.lstrip().startswith("{"):
                return False
            try:
                obj = json.loads(body)
            except ValueError:
                return False
            if not (isinstance(obj, dict) and all(k in obj for k in d["body_json_has"])):
                return False
        if self._body_rx and not self._body_rx.search(body):
            return False
        contains = d.get("body_contains") or []
        if any(s not in body for s in ([contains] if isinstance(contains, str) else contains)):
            return False
        dfc = d.get("delimited_field_count")
        if dfc and len(body.split(dfc["delimiter"])) != int(dfc["count"]):
            return False
        return True


class PackRegistry:
    def __init__(self, extra_dir: Path | None = None, builtin_dir: Path = BUILTIN_DIR):
        self.builtin_dir, self.extra_dir = builtin_dir, extra_dir
        self.reload()

    def reload(self) -> None:
        files = sorted(self.builtin_dir.glob("*.yaml"))
        if self.extra_dir and self.extra_dir.exists():
            files += sorted(self.extra_dir.glob("*.yaml"))
        packs = [Pack(f.read_text(encoding="utf-8")) for f in files]
        self.packs = sorted(packs, key=lambda p: p.priority)

    def detect(self, hs, text: str) -> Pack | None:
        return next((p for p in self.packs if p.detects(hs, text)), None)

    def get(self, name: str) -> Pack | None:
        return next((p for p in self.packs if p.name == name), None)

    @staticmethod
    def load_candidate(yaml_text: str) -> Pack:
        return Pack(yaml_text)
