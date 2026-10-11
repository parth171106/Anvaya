"""Every golden `ocsf` object validates against the vendored schema; invalid objects are caught with a path."""
import copy
import json
from pathlib import Path

import pytest

from app.ocsf.validate import OcsfValidator, main as check_vendored

SAMPLES = Path(__file__).with_name("samples")
NAMES = ["cisco-asa", "suricata-eve", "fortigate-kv", "acme-edge"]
V = OcsfValidator()


def golden(name):
    return json.loads((SAMPLES / name / f"{name}.json").read_text(encoding="utf-8"))["ocsf"]


@pytest.mark.parametrize("name", NAMES)
def test_golden_validates(name):
    assert V(golden(name)) is None


def test_metadata_version_is_the_vendored_one():
    version = (Path(__file__).parents[1] / "app" / "ocsf" / "schema" / "VERSION").read_text().strip()
    assert all(golden(n)["metadata"]["version"] == version for n in NAMES)


@pytest.mark.parametrize("mutate,where", [
    (lambda o: o.pop("time"), "time"),
    (lambda o: o.update(activity_id=42), "activity_id"),
    (lambda o: o.update(bogus_field=1), "bogus_field"),
    (lambda o: o["device"].pop("type_id"), "device"),
])
def test_invalid_objects_rejected_with_path(mutate, where):
    o = copy.deepcopy(golden("cisco-asa"))
    mutate(o)
    err = V(o)
    assert err is not None and where in err


def test_check_vendored_cli(capsys):
    assert check_vendored(["--check-vendored"]) == 0
    assert capsys.readouterr().out.startswith("OK: OCSF ")
