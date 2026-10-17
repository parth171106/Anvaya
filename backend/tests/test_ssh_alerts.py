# ruff: noqa: F811
import json
from unittest.mock import AsyncMock

import pytest
import httpx

from app.delivery import alerts
from app.delivery.alerts import AlertService, TelegramError
from tests.test_correlation import ssh_failures
from tests.test_api_contract import api  # noqa: F401
from tests.test_accounts import multi, multi_cfg, accept_owner, enroll  # noqa: F401
from tests.test_auth import CONSOLE, KEY
from tests.conftest import D
from generator.formats import at

TOKEN = '123456789:' + 'a' * 35


def success(c, seconds=30, device='ssh-test', ip='198.51.100.40'):
    from datetime import datetime, timezone
    stamp = datetime.fromtimestamp((at(D, 10, 0) + seconds * 1000) / 1000, timezone.utc).isoformat()
    c.ingest(f'{stamp} {device} sshd[999]: Accepted publickey for ubuntu from {ip} port 55555 ssh2: RSA synthetic'.encode(), 'http', '127.0.0.1')
    c.worker.drain()


def test_success_escalates_same_incident_across_window_and_keeps_review(c):
    ssh_failures(c, 10)
    first = c.repo.incidents()[0]
    c.repo.update_incident_workflow(first['incident_id'], 'investigating', True, 0, 'Lab run', 'analyst', 'expected')
    success(c, seconds=610)  # outside anchored failure window, inside follow-up period
    inc = c.repo.incidents()[0]
    assert len(c.repo.incidents()) == 1
    assert inc['risk'] == 75 and inc['event_count'] == 11 and inc['stages'] == ['credential', 'access']
    assert inc['workflow']['assessment'] == 'expected'
    detail = c.correlator.detail(inc['incident_id'])
    assert detail['ssh_finding'] and detail['ssh_context_total'] == 1
    assert 'successful SSH' in detail['stages_detail'][1]['headline']
    assert 'Shared IPs' in detail['explanation']
    inbox = c.alerts.listing()
    assert len(inbox['items']) == 2
    c.replays.start([r.raw_id for r in c.repo.raw_records()]); c.worker.drain()
    assert len(c.alerts.listing()['items']) == 2
    c.alerts.acknowledge(inbox['items'][0]['id'])
    assert c.alerts.listing()['unread'] == 1
    assert AlertService(c).listing()['unread'] == 1  # durable across service restart


@pytest.mark.parametrize('kwargs', [{'seconds': -1}, {'seconds': 1000}, {'device': 'other-host'}, {'ip': '198.51.100.99'}])
def test_unrelated_success_never_escalates(c, kwargs):
    ssh_failures(c, 10)
    success(c, **kwargs)
    assert c.repo.incidents()[0]['risk'] == 40
    assert len(c.alerts.listing()['items']) == 1


def test_fewer_than_threshold_is_quiet(c):
    ssh_failures(c, 9)
    success(c)
    assert not c.repo.incidents() and not c.alerts.listing()['items']


async def fake_call(token, method, body):
    if method == 'getMe':
        return {'is_bot': True, 'username': 'anvaya_test_bot'}
    if method == 'getChat':
        return {'id': 12345, 'type': 'private'}
    return {'message_id': 1}


async def test_telegram_configuration_is_private_validated_and_erased(api, monkeypatch):
    provider = AsyncMock(side_effect=fake_call)
    monkeypatch.setattr(alerts, 'telegram_call', provider)
    body = {'bot_token': TOKEN, 'chat_id': '12345', 'consent': True}
    response = await api.post('/api/notifications/telegram', json=body)
    assert response.status_code == 200 and TOKEN not in response.text
    assert TOKEN not in (await api.get('/api/notifications/telegram')).text
    assert json.loads(api.c.alerts.path.read_text())['token'] == TOKEN
    bad = await api.post('/api/notifications/telegram', json={**body, 'consent': 'yes'})
    assert bad.status_code == 422 and TOKEN not in bad.text
    assert (await api.post('/api/notifications/telegram/test')).status_code == 200
    assert provider.call_args.args[1] == 'sendMessage'
    assert 'No incident' in provider.call_args.args[2]['text']
    assert (await api.post('/api/notifications/telegram/disable')).status_code == 200
    assert TOKEN not in api.c.alerts.path.read_text()


async def test_no_group_destination_or_unconsented_setup(c, monkeypatch):
    provider = AsyncMock(side_effect=fake_call)
    monkeypatch.setattr(alerts, 'telegram_call', provider)
    with pytest.raises(ValueError):
        await c.alerts.configure(TOKEN, '-12345', True)
    with pytest.raises(ValueError):
        await c.alerts.configure(TOKEN, '12345', False)
    provider.assert_not_called()
    provider.side_effect = lambda token, method, body: {'is_bot': True} if method == 'getMe' else {'id':12345, 'type':'group'}
    with pytest.raises(ValueError):
        await c.alerts.configure(TOKEN, '12345', True)
    assert not c.alerts.status()['configured']


async def test_delivery_retry_expiry_and_controlled_test_suppression(c, monkeypatch):
    from dataclasses import replace
    c.cfg = replace(c.cfg, demo_mode=False)
    clock = at(D, 10, 0, 30)
    monkeypatch.setattr(alerts, 'now_ms', lambda: clock)
    c.alerts.settings = {'enabled': True, 'token': TOKEN, 'chat_id': '12345'}
    ssh_failures(c, 10)
    assert c.alerts.listing()['items'][0]['delivery'] == 'pending'
    provider = AsyncMock(side_effect=TelegramError('rate_limited', 90))
    monkeypatch.setattr(alerts, 'telegram_call', provider)
    await c.alerts.tick()
    item = c.alerts.listing()['items'][0]
    assert item['attempts'] == 1 and item['next_attempt'] == clock + 90_000
    await c.alerts.tick(); assert provider.call_count == 1
    clock += 91_000
    provider.side_effect = None; provider.return_value = {'message_id': 1}
    await c.alerts.tick()
    assert c.alerts.listing()['items'][0]['delivery'] == 'sent'
    assert '198.51.100.40' in provider.call_args.args[2]['text']
    # Escalation queues once, but analyst classification prevents pending delivery.
    success(c, seconds=120)
    inc = c.repo.incidents()[0]
    c.repo.update_incident_workflow(inc['incident_id'], 'investigating', True, 0, 'Authorized', 'analyst')
    clock += 11_000
    await c.alerts.tick()
    assert c.alerts.listing()['items'][0]['delivery'] == 'suppressed'
    assert provider.call_count == 2
    # A separate finding expires rather than sending stale alerts after downtime.
    ssh_failures(c, 10, ip='198.51.100.50')
    clock += 20 * 60_000
    await c.alerts.tick()
    assert c.alerts.listing()['items'][0]['delivery'] == 'expired'


async def test_historical_and_demo_never_send(c, monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr(alerts, 'telegram_call', provider)
    c.alerts.settings = {'enabled': True, 'token': TOKEN, 'chat_id': '12345'}
    ssh_failures(c, 10)
    assert c.alerts.listing()['items'][0]['historical']
    await c.alerts.tick()
    provider.assert_not_called()


async def test_private_alerts_and_collector_denial(multi):
    app, owner = multi
    assert (await owner.get('/api/alerts')).status_code == 401
    await accept_owner(owner)
    ssh_failures(app.state.workspaces.get('owner'), 10)
    member, _, _ = await enroll(app, owner, 'alert-reviewer')
    try:
        assert (await member.get('/api/alerts')).json()['items'] == []
        assert (await member.post('/api/alerts/1/acknowledge', headers=CONSOLE)).status_code == 404
        assert (await owner.post('/api/alerts/1/acknowledge')).status_code == 403
        assert (await owner.post('/api/alerts/1/acknowledge', headers=CONSOLE)).status_code == 200
        assert (await owner.get('/api/alerts', headers={'Authorization': f'Bearer {KEY}'})).status_code == 403
    finally:
        await member.aclose()


@pytest.mark.parametrize('payload,code,expected', [
    ({'ok': False, 'error_code': 429, 'parameters': {'retry_after': 120}}, 429, 'rate_limited'),
    ({'ok': False, 'error_code': 403}, 403, 'destination_rejected'),
    ([], 200, 'network_or_provider_error'),
])
async def test_provider_errors_do_not_expose_token(monkeypatch, payload, code, expected):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(code, json=payload))
    monkeypatch.setattr(alerts.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=transport, **kwargs))
    with pytest.raises(TelegramError) as caught:
        await alerts.telegram_call(TOKEN, 'sendMessage', {})
    assert caught.value.code == expected and TOKEN not in str(caught.value)
    if code == 429:
        assert caught.value.retry_after == 120


async def test_expected_activity_and_reconfiguration_cancel_pending(c, monkeypatch):
    from dataclasses import replace
    c.cfg = replace(c.cfg, demo_mode=False)
    monkeypatch.setattr(alerts, 'now_ms', lambda: at(D, 10, 0, 30))
    c.alerts.settings = {'enabled': True, 'token': TOKEN, 'chat_id': '12345'}
    provider = AsyncMock(side_effect=fake_call)
    monkeypatch.setattr(alerts, 'telegram_call', provider)
    ssh_failures(c, 10)
    inc = c.repo.incidents()[0]
    c.repo.update_incident_workflow(inc['incident_id'], 'investigating', False, 0, '', 'analyst', 'expected')
    await c.alerts.tick()
    assert c.alerts.listing()['items'][0]['delivery'] == 'suppressed'
    provider.assert_not_called()
    ssh_failures(c, 10, ip='198.51.100.50')
    await c.alerts.configure(TOKEN, '12345', True)
    assert c.alerts.listing()['items'][0]['delivery'] == 'cancelled'


async def test_destination_failure_is_terminal(c, monkeypatch):
    from dataclasses import replace
    c.cfg = replace(c.cfg, demo_mode=False)
    monkeypatch.setattr(alerts, 'now_ms', lambda: at(D, 10, 0, 30))
    c.alerts.settings = {'enabled': True, 'token': TOKEN, 'chat_id': '12345'}
    ssh_failures(c, 10)
    provider = AsyncMock(side_effect=TelegramError('destination_rejected'))
    monkeypatch.setattr(alerts, 'telegram_call', provider)
    await c.alerts.tick()
    assert c.alerts.listing()['items'][0]['delivery'] == 'failed'
    await c.alerts.tick()
    assert provider.call_count == 1
