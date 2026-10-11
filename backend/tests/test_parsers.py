"""Every tests/samples/*/*.log produces its golden *.json envelope (ignoring raw.received_at and raw.batch_id).
Lineage is compared as a set of entries: its order is presentation (the UI orders fields itself)."""
import json
from pathlib import Path

import pytest

from app.parsers.registry import Pack, PackRegistry
from app.pipeline.worker import normalize
from tests.conftest import ocsf_impl

SAMPLES = Path(__file__).with_name("samples")
ACME = Pack((Path(__file__).parents[1] / "app" / "aiparser" / "acme-edge.fallback.yaml").read_text(encoding="utf-8"))
REG = PackRegistry()
ENUMS, VALIDATE = ocsf_impl()


def envelope_for(name):
    golden = json.loads((SAMPLES / name / f"{name}.json").read_text(encoding="utf-8"))
    data = (SAMPLES / name / f"{name}.log").read_bytes()
    r = golden["raw"]
    out = normalize(data, r["raw_id"], r["seq"], r["received_at"], "utf-8", REG, ENUMS, VALIDATE,
                    pack=ACME if name == "acme-edge" else None)
    return golden, data, out


def canonical(env):
    env = json.loads(json.dumps(env))
    env["anvaya"]["lineage"] = sorted(env["anvaya"]["lineage"], key=lambda e: e["path"])
    return env


@pytest.mark.parametrize("name", ["cisco-asa", "suricata-eve", "fortigate-kv", "acme-edge"])
def test_golden_envelope(name):
    golden, data, out = envelope_for(name)
    assert out.reason is None, out.detail
    ev = out.event
    mine = {"event_id": ev.event_id, "raw": {**golden["raw"], "text": data.decode()},  # raw block comes from raw_events
            "ocsf": ev.ocsf, "anvaya": json.loads(ev.anvaya.model_dump_json())}
    assert canonical(mine) == canonical(golden)
    assert ev.event_id == golden["event_id"]


def test_pack_self_tests():
    """The `tests:` blocks inside each pack."""
    from app.ocsf.mapper import get_path
    for pack in REG.packs + [ACME]:
        for t in pack.spec.get("tests", []):
            out = normalize(t["input"].encode(), "r-000000000000", 1, 0, "utf-8", REG, ENUMS, VALIDATE, pack=pack)
            assert out.event, (pack.id, out.detail)
            for path, want in t["expect"].items():
                assert str(get_path(out.event.ocsf, path)) == str(want), (pack.id, path)
