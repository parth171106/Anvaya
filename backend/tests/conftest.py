from datetime import date

import pytest

from app.core import config
from app.core.container import Container
from app.ocsf.enums import Enums
from app.ocsf.validate import OcsfValidator
from generator.scenario import build_scripted_lines

D = date(2026, 9, 30)


_OCSF = None


def ocsf_impl():
    """The vendored OCSF schema (enums + validator), loaded once per test run."""
    global _OCSF
    if _OCSF is None:
        _OCSF = (Enums(), OcsfValidator())
    return _OCSF


@pytest.fixture
def cfg(tmp_path):
    return config.load({"ANVAYA_DEMO_MODE": "1", "ANVAYA_DATA_DIR": str(tmp_path / "data")})


@pytest.fixture
def c(cfg):
    enums, validate = ocsf_impl()
    c = Container(cfg, enums=enums, validate=validate)
    yield c
    c.close_stores()


def ingest_scenario(c, d=D):
    return [c.ingest(text.encode(), "udp", "127.0.0.1") for _, _, text in build_scripted_lines(d)]
