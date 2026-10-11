from pathlib import Path

from app.core import config


def test_defaults():
    c = config.load({})
    assert (c.demo_mode, c.data_dir, c.syslog_udp_port) == (False, Path("/data"), 5514)
    assert (c.ollama_url, c.ollama_model) == ("http://ollama:11434", "qwen2.5:3b")
    assert (c.llm_timeout_s, c.silence_min_seconds) == (15, 60)
    assert (c.seal_batch_size, c.seal_max_age_s, c.seal_max_age_scripted_scn_s) == (16, 5, 300)
    assert (c.display_tz, c.source_tz_default) == ("Asia/Kolkata", "Asia/Kolkata")


def test_demo_mode_defaults():
    c = config.load({"ANVAYA_DEMO_MODE": "1"})
    assert (c.demo_mode, c.llm_timeout_s, c.silence_min_seconds) == (True, 5, 15)
