"""Recovery tests use isolated synthetic accounts."""
from contextlib import aclosing

import httpx

from app.auth import digest
from tests.test_accounts import accept_owner, enroll
from tests import test_accounts as account_tests
from tests.test_auth import CONSOLE, PASSWORD, KEY

NEW = 'a different synthetic password 456!'
multi, multi_cfg = account_tests.multi, account_tests.multi_cfg


async def test_code_reset_invalidates_sessions_and_is_single_use(multi):
    app, owner = multi
    await accept_owner(owner)
    member, aid, _ = await enroll(app, owner, 'alice')
    async with aclosing(member), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=owner.base_url) as anon:
        code = (await member.post('/api/account/recovery-code', json={'password': PASSWORD}, headers=CONSOLE)).json()['code']
        assert app.state.auth.accounts.con.execute('SELECT code_hash FROM recovery_settings WHERE account_id=?', (aid,)).fetchone()[0] == digest(code)
        assert 'code_hash' not in (await member.get('/api/account')).text
        assert (await anon.post('/api/auth/reset-password', json={'username': 'admin', 'code': code, 'password': NEW}, headers=CONSOLE)).status_code == 400
        result = await anon.post('/api/auth/reset-password', json={'username': 'alice', 'code': code, 'password': NEW}, headers=CONSOLE)
        assert result.status_code == 200
        assert (await member.get('/api/account')).status_code == 401
        assert (await owner.get('/api/account')).status_code == 200
        assert (await anon.get('/api/auth/session')).json()['authenticated'] is False
        assert (await anon.post('/api/auth/reset-password', json={'username': 'alice', 'code': code, 'password': NEW}, headers=CONSOLE)).status_code == 400
        assert (await anon.post('/api/auth/login', json={'username': 'alice', 'password': PASSWORD}, headers=CONSOLE)).status_code == 401
        assert (await anon.post('/api/auth/login', json={'username': 'alice', 'password': NEW}, headers=CONSOLE)).status_code == 200
        # Recovery doesn't silently replace ingestion-only keys.
        assert (await anon.get('/api/health', headers={'Authorization': f'Bearer {KEY}'})).status_code == 200


async def test_proof_required_rotation_disabled_account_and_body_limits(multi):
    app, owner = multi
    await accept_owner(owner)
    member, aid, _ = await enroll(app, owner, 'alice')
    async with aclosing(member):
        assert (await member.post('/api/account/recovery-code', json={'password': 'wrong'}, headers=CONSOLE)).status_code == 400
        old = (await member.post('/api/account/recovery-code', json={'password': PASSWORD}, headers=CONSOLE)).json()['code']
        new = (await member.post('/api/account/recovery-code', json={'password': PASSWORD}, headers=CONSOLE)).json()['code']
        assert old != new
        assert (await member.post('/api/auth/reset-password', json={'username': 'alice', 'code': old, 'password': NEW}, headers=CONSOLE)).status_code == 400
        assert (await member.post('/api/auth/reset-password', json={'username': 'alice', 'code': new, 'password': 'short'}, headers=CONSOLE)).status_code == 422
        assert (await member.post('/api/auth/reset-password', json={'code': 'SECRET' * 2000}, headers=CONSOLE)).status_code == 413
        assert (await member.post('/api/auth/reset-password', json={'username': 'alice', 'code': new, 'password': NEW})).status_code == 403
        app.state.auth.accounts.disable(aid)
        assert (await owner.post('/api/auth/reset-password', json={'username': 'alice', 'code': new, 'password': NEW}, headers=CONSOLE)).status_code == 400


async def test_rate_limit(multi):
    app, client = multi
    assert (await client.get('/api/auth/recovery-options')).json() == {'code_available': True}
    for _ in range(10):
        assert (await client.post('/api/auth/reset-password', json={'username': 'missing', 'code': 'wrong', 'password': NEW}, headers=CONSOLE)).status_code == 400
    assert (await client.post('/api/auth/reset-password', json={'password': NEW}, headers=CONSOLE)).status_code == 429


async def test_signup_code_and_no_secret_validation_leak(multi):
    app, owner = multi
    await accept_owner(owner)
    app.state.auth.accounts.public_signup = True
    from app.accounts import TERMS_VERSION
    result = await owner.post('/api/auth/register', json={'username': 'new-user', 'password': PASSWORD, 'terms_version': TERMS_VERSION}, headers=CONSOLE)
    assert result.status_code == 201 and len(result.json()['recovery_code']) >= 40
    bad = await owner.post('/api/auth/reset-password', json={'password': ['DO-NOT-ECHO'], 'code': 'SECRET-CODE'}, headers=CONSOLE)
    assert bad.status_code == 422 and 'DO-NOT-ECHO' not in bad.text and 'SECRET-CODE' not in bad.text


async def test_saved_code_persists_and_email_routes_are_absent(multi):
    from app.recovery import Recovery
    app, owner = multi
    await accept_owner(owner)
    code = (await owner.post('/api/account/recovery-code', json={'password': PASSWORD}, headers=CONSOLE)).json()['code']
    app.state.auth.recovery = Recovery(app.state.auth.accounts)
    profile = (await owner.get('/api/account')).json()
    assert profile['has_recovery_code'] is True and 'recovery_email' not in profile
    for path in ('/api/account/recovery-email', '/api/auth/verify-email', '/api/auth/forgot-password'):
        assert (await owner.post(path, json={}, headers=CONSOLE)).status_code == 404
    result = await owner.post('/api/auth/reset-password', json={'username': 'admin', 'code': code, 'password': NEW}, headers=CONSOLE)
    assert result.status_code == 200
