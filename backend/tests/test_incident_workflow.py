# Imported pytest fixtures are intentionally requested by name in test signatures.
# ruff: noqa: F811
import pytest

from app.storage.sqlite_repo import SqliteRepository
from tests.conftest import ingest_scenario
from tests.test_api_contract import api  # noqa: F401
from tests.test_accounts import multi, multi_cfg, accept_owner, enroll  # noqa: F401
from tests.test_auth import CONSOLE, KEY


def seed(c):
    ingest_scenario(c)
    c.worker.drain()
    return c.repo.incidents()[0]['incident_id']


def update(version=0, state='investigating', note='Reviewed linked evidence.', controlled_test=True):
    return dict(version=version, state=state, note=note, controlled_test=controlled_test)


async def test_workflow_persists_recorrelation_and_preserves_evidence(api):
    iid = seed(api.c)
    raw_before = [(r.raw_id, api.c.store.read(r.raw_id)) for r in api.c.repo.raw_records()]
    first = await api.post(f'/api/incidents/{iid}/investigation', json=update())
    assert first.status_code == 200, first.text
    assert first.json()['workflow'] == dict(state='investigating', controlled_test=True, version=1)
    assert first.json()['activity'][0]['note'] == 'Reviewed linked evidence.'
    closed = await api.post(f'/api/incidents/{iid}/investigation', json=update(1, 'resolved', 'Authorized test.'))
    assert closed.json()['status'] == 'closed'
    assert (await api.get('/api/stats')).json()['open_incidents'] == 0
    # New correlation passes must not erase the analyst's decision or annotations.
    seed(api.c)
    assert api.c.correlator.summary(iid)['workflow']['state'] == 'resolved'
    assert [(rid, api.c.store.read(rid)) for rid, _ in raw_before] == raw_before
    reopened = await api.post(f'/api/incidents/{iid}/investigation', json=update(2, 'investigating', 'Reopened for review.'))
    assert reopened.json()['status'] == 'open'
    assert (await api.get('/api/stats')).json()['open_incidents'] == 1
    reopened_repo = SqliteRepository(api.c.repo.path)
    try:
        assert reopened_repo.incident_summary(iid)['workflow']['version'] == 3
        assert len(reopened_repo.incident_activity(iid)) == 3
    finally:
        reopened_repo.close()


async def test_conflict_is_atomic_and_notes_are_plain_text(api):
    iid = seed(api.c)
    note = '<script>alert("test")</script>\nReview only'
    assert (await api.post(f'/api/incidents/{iid}/investigation', json=update(note=note))).status_code == 200
    conflict = await api.post(f'/api/incidents/{iid}/investigation', json=update(state='resolved'))
    assert conflict.status_code == 409
    result = (await api.get(f'/api/incidents/{iid}')).json()
    assert result['workflow']['version'] == 1 and result['status'] == 'open'
    assert len(result['activity']) == 1 and result['activity'][0]['note'] == note


@pytest.mark.parametrize('patch', [{'state': 'deleted'}, {'note': 'x' * 5001}, {'version': -1},
                                  {'version': True}, {'controlled_test': 'false'}, {'actor': 'admin'}])
async def test_invalid_updates_rejected(api, patch):
    iid = seed(api.c)
    assert (await api.post(f'/api/incidents/{iid}/investigation', json=update() | patch)).status_code == 422
    assert api.c.repo.incident_activity(iid) == []


async def test_workspace_isolation_auth_and_csrf(multi):
    app, owner = multi
    endpoint = '/api/incidents/inc-0001/investigation'
    assert (await owner.post(endpoint, json=update(), headers=CONSOLE)).status_code == 401
    await accept_owner(owner)
    seed(app.state.workspaces.get('owner'))
    member, account_id, _ = await enroll(app, owner, 'case-reviewer')
    try:
        assert (await member.post(endpoint, json=update(), headers=CONSOLE)).status_code == 404
        seed(app.state.workspaces.get(account_id))  # same ID, different workspace
        result = await member.post(endpoint, json=update(note='Private member note'), headers=CONSOLE)
        assert result.status_code == 200 and result.json()['activity'][0]['actor'] == 'case-reviewer'
        assert (await owner.get('/api/incidents/inc-0001')).json()['activity'] == []
        assert (await owner.post(endpoint, json=update())).status_code == 403
        assert (await owner.post(endpoint, json=update(), headers={'Authorization': f'Bearer {KEY}'})).status_code == 403
    finally:
        await member.aclose()
