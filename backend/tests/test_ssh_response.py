# ruff: noqa: F811
from dataclasses import replace

import pytest

from app.delivery.response_plan import prepare
from collectors.ssh_response import validate_plan, rules, protections
from tests.test_correlation import ssh_failures
from tests.test_accounts import multi, multi_cfg, accept_owner, enroll  # noqa: F401
from tests.test_auth import CONSOLE, KEY


def plan(**changes):
    return dict(version=1, action='block-new-ssh', plan_id='a' * 32, device='server',
                source_ip='8.8.8.8', minutes=5, created_at=1000, expires_at=1600, **changes)


@pytest.mark.parametrize('changes', [
    {'minutes': 0}, {'minutes': True}, {'minutes': 60}, {'source_ip': '127.0.0.1'},
    {'source_ip': '10.0.0.1'}, {'source_ip': '198.51.100.9'}, {'source_ip': '224.0.0.1'},
    {'source_ip': '8.8.8.8; flush ruleset'}, {'device': 'another-host'},
    {'plan_id': 'x; flush ruleset'}, {'created_at': 1}, {'expires_at': 1001},
])
def test_rejects_unsafe_plans(changes):
    candidate = {**plan(), **changes}
    with pytest.raises(ValueError):
        validate_plan(candidate, 'server', ['1.1.1.1'], now=1100)


def test_management_ranges_and_ipv6():
    with pytest.raises(ValueError):
        validate_plan(plan(), 'server', ['8.8.8.0/24'], now=1100)
    candidate = {**plan(), 'source_ip': '2606:4700:4700::1111'}
    address = validate_plan(candidate, 'server', ['1.1.1.1'], now=1100)
    script = rules(candidate, address, 2222)
    assert 'ip6 saddr' in script and 'timeout 5m' in script and 'tcp dport 2222' in script
    assert 'ct state new' in script and 'flush' not in script and 'policy accept' in script


def test_connected_ssh_and_local_addresses_protected(monkeypatch):
    from collectors import ssh_response
    monkeypatch.setenv('SSH_CONNECTION', '8.8.4.4 2345 10.0.0.2 22')
    outputs = iter(['[{"addr_info":[{"local":"10.0.0.2"}]}]',
                    '0 0 10.0.0.2:22 8.8.8.8:12345\n0 0 [::1]:22 [2606:4700:4700::1111]:12345'])
    monkeypatch.setattr(ssh_response, 'run', lambda *args: next(outputs))
    protected = protections('ip', 'ss', 22, ['1.1.1.0/24'])
    assert set(protected) == {'10.0.0.2', '8.8.8.8', '8.8.4.4', '2606:4700:4700::1111', '1.1.1.0/24'}
    with pytest.raises(ValueError):
        validate_plan(plan(), 'server', protected, now=1100)


def test_requires_review_and_real_public_source(c):
    c.cfg = replace(c.cfg, demo_mode=False)
    ssh_failures(c, 10, ip='8.8.8.8', device='server')  # Synthetic fixture; no network traffic.
    iid = c.repo.incidents()[0]['incident_id']
    with pytest.raises(ValueError):
        prepare(c, iid, 'server', 5, 'analyst')
    c.repo.update_incident_workflow(iid, 'investigating', False, 0, 'Reviewed', 'analyst', 'suspicious')
    result = prepare(c, iid, 'server', 5, 'analyst')
    assert result['expires_at'] - result['created_at'] == 600
    assert result['action'] == 'block-new-ssh'
    validate_plan(result, 'server', ['1.1.1.1'])
    c.repo.update_incident_workflow(iid, 'investigating', True, 1, '', 'analyst', 'suspicious')
    with pytest.raises(ValueError):
        prepare(c, iid, 'server', 5, 'analyst')


async def test_block_plan_private_and_not_available_to_collector(multi):
    app, owner = multi
    body = {'device': 'server', 'minutes': 5}
    await accept_owner(owner)
    c = app.state.workspaces.get('owner')
    ssh_failures(c, 10, ip='8.8.8.8', device='server')
    iid = c.repo.incidents()[0]['incident_id']
    c.repo.update_incident_workflow(iid, 'investigating', False, 0, '', 'analyst', 'suspicious')
    path = f'/api/incidents/{iid}/block-plan'
    assert (await owner.post(path, json=body)).status_code == 403
    assert (await owner.post(path, json=body, headers=CONSOLE)).status_code == 200
    assert (await owner.post(path, json=body, headers={'Authorization': f'Bearer {KEY}'})).status_code == 403
    member, _, _ = await enroll(app, owner, 'response-reviewer')
    try:
        assert (await member.post(path, json=body, headers=CONSOLE)).status_code == 404
    finally:
        await member.aclose()
