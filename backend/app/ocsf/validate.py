"""Validate OCSF objects against the vendored JSON Schema (TRD.md §7.3). `python -m app.ocsf.validate --check-vendored`
backs `make check-ocsf`.

jsonschema re-resolves $refs on every call (~6 ms per event), so results are cached by the object's *shape*: its keys,
each leaf's type, and the values of the only properties the schema constrains by value (enum/const ids). At load time
the schema is scanned; if it constrains any other value (pattern, ranges, other enums), the cache is switched off."""
import argparse
import sys

from jsonschema import Draft202012Validator, validators

from app.ocsf.enums import CLASS_FILES, SCHEMA_DIR, Enums, load_class

RANGE_KEYWORDS = {"pattern", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
                  "multipleOf", "minItems", "maxItems", "uniqueItems", "patternProperties", "propertyNames"}
CACHE_MAX = 4096


def _value_keyed(name: str) -> bool:
    return name.endswith(("_id", "_uid"))


def value_constraints(schema) -> set[str]:
    """Constraints the shape cache can't see: range/pattern keywords, or enum/const on a non-*_id property."""
    found: set[str] = set()

    def walk(n):
        if isinstance(n, dict):
            found.update(k for k in n if k in RANGE_KEYWORDS)
            for k, v in (n.get("properties") or {}).items():
                if isinstance(v, dict) and ("enum" in v or "const" in v) and not _value_keyed(k):
                    found.add(f"enum:{k}")
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(schema)
    return found


def shape_key(o, name: str = ""):
    if name == "unmapped":  # $defs/object: additionalProperties true, no constraints inside
        return "object" if isinstance(o, dict) else type(o).__name__
    if isinstance(o, dict):
        return tuple(sorted((k, shape_key(v, k)) for k, v in o.items()))
    if isinstance(o, list):
        return ("[", tuple(shape_key(v, name) for v in o))
    if _value_keyed(name):
        return ("=", o)
    return type(o).__name__


class OcsfValidator:
    def __init__(self, schema_dir=SCHEMA_DIR):
        self.validators, self.cacheable, self.cache = {}, {}, {}
        for uid, name in CLASS_FILES.items():
            schema = load_class(name, schema_dir)
            cls = validators.validator_for(schema, default=Draft202012Validator)
            cls.check_schema(schema)
            self.validators[uid] = cls(schema)
            # Only enum-carrying properties the stored objects never use ('depth', 'http_method', 'tlp') are allowed.
            self.cacheable[uid] = value_constraints(schema) <= {"enum:depth", "enum:http_method", "enum:tlp"}

    def _validate(self, v, ocsf: dict) -> str | None:
        err = next(iter(sorted(v.iter_errors(ocsf), key=lambda e: list(e.absolute_path))), None)
        if err is None:
            return None
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        return f"{path}: {err.message[:200]}"

    def __call__(self, ocsf: dict) -> str | None:
        """None if valid, else '<path>: <message>' for the first error."""
        uid = ocsf.get("class_uid")
        v = self.validators.get(uid)
        if v is None:
            return f"class_uid: unsupported class {uid}"
        if not self.cacheable[uid] or self._uses_unkeyed_enum(ocsf):
            return self._validate(v, ocsf)
        key = shape_key(ocsf)
        if key not in self.cache:
            if len(self.cache) >= CACHE_MAX:
                self.cache.clear()
            self.cache[key] = self._validate(v, ocsf)
        return self.cache[key]

    @staticmethod
    def _uses_unkeyed_enum(o) -> bool:
        if isinstance(o, dict):
            return any(k in ("depth", "http_method", "tlp") or OcsfValidator._uses_unkeyed_enum(v) for k, v in o.items())
        if isinstance(o, list):
            return any(OcsfValidator._uses_unkeyed_enum(v) for v in o)
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-vendored", action="store_true")
    ap.add_argument("--app-dir", default=None, help="ignored; kept for the Makefile target")
    ap.parse_args(argv)
    try:
        OcsfValidator()
        e = Enums()
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"OK: OCSF {e.version}, classes {sorted(CLASS_FILES.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
