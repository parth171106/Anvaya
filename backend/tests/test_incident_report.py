# ruff: noqa: F811
from io import BytesIO

from pypdf import PdfReader

from app.delivery import incident_report as reports
from tests.conftest import ingest_scenario
from tests.test_api_contract import api  # noqa: F401
from tests.test_accounts import multi, multi_cfg, accept_owner, enroll  # noqa: F401
from tests.test_auth import CONSOLE, KEY


def seed(c):
    ingest_scenario(c)
    c.worker.drain()
    while c.ledger.unsealed:
        c.ledger.seal()
    return c.repo.incidents()[0]['incident_id']


def text(pdf):
    return '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)


def test_fresh_proofs_detect_tampering_without_mutation(c):
    iid = seed(c)
    before = c.repo.get_meta('last_verify')
    good = reports.snapshot(c, iid)
    assert good['status'] == 'VERIFIED'
    assert good['counts']['VERIFIED'] == len(good['events'])
    assert c.repo.get_meta('last_verify') == before
    raw_id = good['events'][0]['raw_id']
    raw = c.store.read(raw_id)
    c.store.overwrite_byte_for_demo(raw_id, 0, raw[0] ^ 1)
    bad = reports.snapshot(c, iid)
    assert bad['status'] == 'FAILED'
    assert bad['checks'][raw_id]['status'] == 'FAILED'
    assert bad['checks'][raw_id]['stored_hash'] != bad['checks'][raw_id]['current_hash']
    assert 'FAILED' in text(reports.render_pdf(bad))


def test_skipped_pending_missing_and_partial_never_claim_verified(c, monkeypatch):
    iid = seed(c)
    def forbidden(_):
        raise AssertionError('Skipped exports must not verify')
    original = c.ledger.verify_record
    monkeypatch.setattr(c.ledger, 'verify_record', forbidden)
    skipped = reports.snapshot(c, iid, False)
    assert skipped['status'] == 'NOT CHECKED'
    monkeypatch.setattr(c.ledger, 'verify_record', lambda _: None)
    pending = reports.snapshot(c, iid)
    assert pending['status'] == 'NOT CHECKED'
    assert 'not sealed' in next(iter(pending['checks'].values()))['reason']
    def unavailable(_):
        raise OSError('private filesystem path')
    monkeypatch.setattr(c.ledger, 'verify_record', unavailable)
    missing = reports.snapshot(c, iid)
    assert missing['status'] == 'NOT CHECKED'
    assert 'private filesystem path' not in text(reports.render_pdf(missing))
    monkeypatch.setattr(c.ledger, 'verify_record', original)
    monkeypatch.setattr(reports, 'MAX_EVENTS', 2)
    partial = reports.snapshot(c, iid)
    assert len(partial['events']) == 2 and partial['omitted'] > 0
    assert partial['status'] == 'NOT CHECKED' and partial['counts']['VERIFIED'] == 2
    monkeypatch.setattr(c.repo, 'summaries', lambda _: [])
    empty = reports.snapshot(c, iid)
    assert empty['status'] == 'NOT CHECKED' and empty['omitted'] == empty['event_total']
    assert 'No linked normalized events are available' in text(reports.render_pdf(empty))


async def test_pdf_download_notes_headers_and_plain_text(api):
    iid = seed(api.c)
    note = '<a href="https://invalid.test">Plain note</a> & review 🔒\n' + ('Long analyst note. ' * 200)
    api.c.repo.update_incident_workflow(iid, 'investigating', True, 0, note, 'Test analyst')
    response = await api.post(f'/api/incidents/{iid}/report', json={'verify': True})
    assert response.status_code == 200, response.text[:100]
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert 'attachment;' in response.headers['content-disposition']
    assert response.content.startswith(b'%PDF-')
    content = text(response.content)
    for expected in ['CONTROLLED TEST', 'DEMO MODE', 'VERIFIED', 'Test analyst', 'Plain note', '[U+1F512]',
                     'full chain history', 'Stored SHA-256', iid]:
        assert expected in content
    assert not any(page.get('/Annots') for page in PdfReader(BytesIO(response.content)).pages)
    assert (await api.post(f'/api/incidents/{iid}/report', json={'verify': 'true'})).status_code == 422
    assert (await api.post('/api/incidents/missing/report', json={})).status_code == 404


async def test_report_auth_csrf_and_same_id_workspace_isolation(multi):
    app, owner = multi
    endpoint = '/api/incidents/inc-0001/report'
    assert (await owner.post(endpoint, json={}, headers=CONSOLE)).status_code == 401
    await accept_owner(owner)
    c = app.state.workspaces.get('owner')
    iid = seed(c)
    endpoint = f'/api/incidents/{iid}/report'
    c.repo.update_incident_workflow(iid, 'investigating', True, 0, 'OWNER SECRET NOTE', 'admin')
    member, aid, _ = await enroll(app, owner, 'report-reader')
    try:
        assert (await member.post(endpoint, json={}, headers=CONSOLE)).status_code == 404
        seed(app.state.workspaces.get(aid))
        result = await member.post(endpoint, json={}, headers=CONSOLE)
        assert result.status_code == 200
        assert 'OWNER SECRET NOTE' not in text(result.content)
        assert 'OWNER SECRET NOTE' in text((await owner.post(endpoint, json={}, headers=CONSOLE)).content)
        assert (await owner.post(endpoint, json={})).status_code == 403
        assert (await owner.post(endpoint, json={}, headers={'Authorization': f'Bearer {KEY}'})).status_code == 403
    finally:
        await member.aclose()
