import json
from pathlib import Path

import pytest

from app.aiparser.drafts import DraftError, DraftService
from app.aiparser.sources import CachedDraftSource, DraftUnavailable, LiveDraftSource
from generator.br01 import build_br01_lines
from generator.formats import at
from tests.conftest import D

FALLBACK = (Path(__file__).parents[1] / "app" / "aiparser" / "acme-edge.fallback.yaml").read_text(encoding="utf-8")


def hand_authored_cache(tmp_path, yaml_text=FALLBACK):
    f = tmp_path / "acme-edge.json"
    f.write_text(json.dumps({"group_shape": "EDGE|x12", "origin": "hand_authored", "model": None,
                             "generated_at": 1, "yaml": yaml_text}), encoding="utf-8")
    return f


@pytest.fixture
def q(c, tmp_path):
    """br01's 20 lines sitting in quarantine, and a DraftService over a hand-authored cache."""
    seen = []
    c.publish = lambda e, d: seen.append((e, d))
    for ln in build_br01_lines(at(D, 10, 14, 3)):
        c.ingest(ln.encode(), "http", "127.0.0.1")
    c.worker.drain()
    c.drafts = DraftService(c, CachedDraftSource(hand_authored_cache(tmp_path)))
    c.seen = seen
    return c


def group(c):
    return c.repo.quarantine_groups()[0]["group_id"]


async def test_draft_test_approve_replay(q):
    d = await q.drafts.create(group(q))
    assert (d["draft_id"], d["status"], d["origin"], d["model"]) == ("dr-0001", "drafted", "hand_authored", None)
    assert (d["train_count"], d["holdout_count"], d["holdout_indexes"]) == (14, 6, [2, 5, 8, 11, 14, 17])
    assert (await q.drafts.create(group(q)))["draft_id"] == d["draft_id"]

    t = q.drafts.test("dr-0001")
    assert t["promotable"] and t["failures"] == []
    assert (t["holdout"], t["all"], t["ocsf_valid"]) == ({"passed": 6, "total": 6}, {"passed": 20, "total": 20},
                                                          {"passed": 20, "total": 20})
    assert t["roundtrip"] == {"passed": 20, "total": 20, "min_coverage": 1.0}
    assert [s["index"] for s in t["samples"]] == [2, 5, 8, 11, 14, 17]
    resumed = await q.drafts.create(group(q))
    assert resumed["draft_id"] == d["draft_id"] and resumed["test"]["promotable"]
    assert q.repo.con.execute("SELECT COUNT(*) FROM parser_drafts").fetchone()[0] == 1

    a = q.drafts.approve("dr-0001", "analyst@ntro-demo")
    assert a == {"parser": {"name": "acme-edge", "version": "1.0.0", "status": "active"}, "replay_id": "rp-0001",
                 "queued": 20}
    assert (q.cfg.data_dir / "packs" / "acme-edge.yaml").read_text(encoding="utf-8") == FALLBACK
    q.worker.drain()
    assert q.repo.quarantine_total() == 0
    assert ("replay.completed", {"replay_id": "rp-0001", "parsed": 20, "still_quarantined": 0}) in q.seen
    assert ("parser.approved", {"name": "acme-edge", "version": "1.0.0", "group_id": group_of_events(q),
                                "replay_id": "rp-0001"}) in q.seen
    br = [p for p in q.repo.parsers() if p["name"] == "acme-edge"][0]
    assert (br["origin"], br["approved_by"], br["events_parsed"], br["roundtrip_pass_rate"]) == \
        ("user", "analyst@ntro-demo", 20, 1.0)
    assert q.repo.con.execute("SELECT COUNT(*) FROM audit_log WHERE action='parser.approve'").fetchone()[0] == 1
    assert q.stats()["formats_detected"] == 1 and q.stats()["parse_coverage_pct"] == 100.0


def group_of_events(c):
    return next(d["group_id"] for e, d in c.seen if e == "event.quarantined")


async def test_approve_before_test_is_409(q):
    await q.drafts.create(group(q))
    with pytest.raises(DraftError) as e:
        q.drafts.approve("dr-0001", "x")
    assert (e.value.status, e.value.code) == (409, "not_promotable")


async def test_broken_yaml_not_promotable(q, tmp_path):
    broken = FALLBACK.replace("columns: [marker, ts, host,", "columns: [marker, host, ts,")  # swaps two columns
    q.drafts = DraftService(q, CachedDraftSource(hand_authored_cache(tmp_path, broken)))
    await q.drafts.create(group(q))
    t = q.drafts.test("dr-0001")
    assert not t["promotable"] and t["all"]["passed"] == 0
    assert t["failures"][0]["check"] == "parse" and "parse_error" in t["failures"][0]["detail"]
    with pytest.raises(DraftError):
        q.drafts.approve("dr-0001", "x")


async def test_unparseable_yaml_reports_load_failure(q, tmp_path):
    q.drafts = DraftService(q, CachedDraftSource(hand_authored_cache(tmp_path, "name: [unclosed")))
    await q.drafts.create(group(q))
    t = q.drafts.test("dr-0001")
    assert not t["promotable"] and t["failures"][0]["check"] == "load"


async def test_missing_cache_is_unavailable(q, tmp_path):
    q.drafts = DraftService(q, CachedDraftSource(tmp_path / "nope.json"))
    with pytest.raises(DraftUnavailable, match="make prebake"):
        await q.drafts.create(group(q))


async def test_reject(q):
    await q.drafts.create(group(q))
    assert q.drafts.reject("dr-0001", "wrong field order") == {"draft_id": "dr-0001", "status": "rejected"}


class OfflineDraftModel:
    async def ready(self):
        return False

    async def complete(self, *args, **kwargs):
        raise AssertionError("No model should receive known-template samples or run while offline")


async def test_known_edge_template_without_model(q):
    q.drafts = DraftService(q, LiveDraftSource(OfflineDraftModel()))
    draft = await q.drafts.create(group(q))
    assert draft["origin"] == "hand_authored"
    assert draft["model"] is None and draft["generated_at"] is None
    assert "origin: user" in draft["yaml"]
    with pytest.raises(DraftError, match="All four checks"):
        q.drafts.approve(draft["draft_id"], "tester")
    result = q.drafts.test(draft["draft_id"])
    assert result["promotable"] and result["all"] == {"passed": 20, "total": 20}
    q.drafts.approve(draft["draft_id"], "tester")
    q.worker.drain()
    assert q.repo.quarantine_total() == 0
    assert next(p for p in q.repo.parsers() if p["name"] == "acme-edge")["origin"] == "user"
    q.close_stores()
    q.open_stores()
    assert next(p for p in q.repo.parsers() if p["name"] == "acme-edge")["origin"] == "user"


@pytest.mark.parametrize("change", [lambda line: line.replace("EDGE|", "OTHER|"),
                                    lambda line: line.replace("|SESSION|", "|AUTH|"),
                                    lambda line: line.replace("bytes=", "duration="),
                                    lambda line: line.replace("rule=", "account=")])
async def test_similar_shape_does_not_get_unrelated_template(change):
    source = LiveDraftSource(OfflineDraftModel())
    line = build_br01_lines(at(D, 10, 14, 3))[0]
    with pytest.raises(DraftUnavailable, match="No bundled parser template matches"):
        await source.draft("group", [change(line)], "EDGE|x12")


async def test_unknown_format_uses_available_local_model():
    class AvailableModel:
        model = "test-model"

        async def ready(self):
            return True

        async def complete(self, system, prompt, timeout_s, **kwargs):
            assert "OTHER|value" in prompt
            return "```yaml\nname: example\n```"

    draft = await LiveDraftSource(AvailableModel()).draft("group", ["OTHER|value"], "OTHER|x2")
    assert draft.origin == "llm_live" and draft.model == "test-model"
    assert draft.yaml == "name: example"


async def test_template_gates_still_reject_malformed_input(q):
    # Keep a matching known-format shape but corrupt a required typed field.
    lines = build_br01_lines(at(D, 10, 14, 3))
    source = LiveDraftSource(OfflineDraftModel())
    draft = await source.draft("group", [lines[0]], "EDGE|x12")
    from app.aiparser.drafts import run_gates
    bad = lines[0].split("|")
    bad[6] = "not-an-ip"
    result = run_gates(draft.yaml, ["|".join(bad)], [0], q.enums, q.validate)
    assert not result["promotable"] and result["all"]["passed"] == 0
