from unittest.mock import AsyncMock
from datetime import timedelta

import pytest

from app.api.errors import ApiError
from app.search.incidents import incident_answer
from tests.conftest import D, ingest_scenario
from generator.formats import at


@pytest.fixture
def incidents(c, monkeypatch):
    ingest_scenario(c)
    c.worker.drain()
    monkeypatch.setattr(c.clock, "now_ms", lambda: at(D + timedelta(days=1), 12, 0))
    c.assistant.provider.configured = lambda: True
    c.assistant.provider.complete = AsyncMock(side_effect=AssertionError("Incident lookups must stay local"))
    c.llm.ready = AsyncMock(side_effect=AssertionError("Incident lookups must stay local"))
    return c


@pytest.mark.parametrize("question", ["show me any intrusion", "Show detected incidents", "any intrusions?", "Are there any attacks?", "Show suspicious activity"])
async def test_intrusion_intent_returns_detected_incidents_without_provider(incidents, question):
    for r in [await incidents.search.answer(question), await incidents.assistant.search(question, True)]:
        assert r["result_type"] == "incidents" and r["row_count"] == 1
        assert r["incidents"][0]["event_count"] == 56
        assert r["incidents"][0]["risk"] == 95
        assert r["model"] is None and r["engine"] == "template"
    incidents.assistant.provider.complete.assert_not_called()


async def test_incident_followup_preserves_date_and_resolves_source_or_target(incidents):
    first = await incidents.assistant.search("Show incidents yesterday", True)
    second = await incidents.assistant.search("Only show those from 198.51.100.9", True, first["query_id"])
    assert second["row_count"] == 1
    assert second["params"]["from_ms"] == first["params"]["from_ms"]
    third = await incidents.assistant.search("Only from 10.2.4.18", True, second["query_id"])
    assert third["row_count"] == 1
    fourth = await incidents.assistant.search("Only from 192.0.2.99", True, third["query_id"])
    assert fourth["row_count"] == 0
    assert (await incidents.assistant.search("Show incidents today", True))["row_count"] == 0


@pytest.mark.parametrize("question", ["show incidents from not-a-real-ip", "show intrusions tomorrow", "show incidents from 999.1.1.1", "show incidents from 1.2.3.4 OR 1=1", "show incidents not from 198.51.100.9"])
async def test_unsupported_filters_do_not_silently_broaden_results(incidents, question):
    with pytest.raises(ApiError) as exc:
        await incidents.assistant.search(question, True)
    assert exc.value.code == "incident_filter"


def test_literal_event_text_does_not_become_incident_intent(incidents):
    assert incident_answer(incidents.search, "Show events with title containing intrusion") is None
    assert incident_answer(incidents.search, "Show failed SSH logins") is None


async def test_empty_workspace_does_not_invent_an_incident(c):
    r = await c.search.answer("show me any intrusion")
    assert r["result_type"] == "incidents" and r["row_count"] == 0 and not r["incidents"]
