"""Private, durable SSH alerts. Telegram is opt-in and receives only a small summary."""
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import os
import re
import time
from uuid import uuid4

import httpx


def now_ms():
    return int(time.time() * 1000)


class TelegramError(Exception):
    def __init__(self, code, retry_after=0):
        self.code, self.retry_after = code, retry_after
        super().__init__(code)  # Never include token-bearing request URLs or provider response text.


async def telegram_call(token, method, body):
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.post(f'https://api.telegram.org/bot{token}/{method}', json=body)
        result = response.json()
        if not response.is_success or not result.get('ok'):
            code = result.get('error_code', response.status_code)
            delay = result.get('parameters', {}).get('retry_after', 0)
            raise TelegramError('rate_limited' if code == 429 else 'destination_rejected' if code in (400, 401, 403)
                                else 'provider_unavailable', min(3600, max(0, int(delay))))
        return result['result']
    except TelegramError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        raise TelegramError('network_or_provider_error') from None


class AlertService:
    def __init__(self, c):
        self.c, self.repo = c, c.repo
        self.path = c.cfg.data_dir / 'notifications' / 'telegram.json'
        self.lock = asyncio.Lock()
        self.last_setup = 0
        self.settings = {}
        if self.path.exists():
            self.settings = json.loads(self.path.read_text(encoding='utf-8'))
        self.repo.con.executescript('''
            CREATE TABLE IF NOT EXISTS security_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
                kind TEXT NOT NULL, created_at INTEGER NOT NULL, event_time INTEGER NOT NULL,
                payload TEXT NOT NULL, seen_at INTEGER, historical INTEGER NOT NULL,
                delivery TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt INTEGER NOT NULL DEFAULT 0, last_error TEXT, sent_at INTEGER,
                UNIQUE(incident_id, kind));
            CREATE INDEX IF NOT EXISTS security_alert_delivery ON security_alerts(delivery, next_attempt);
        ''')

    def status(self):
        return {'enabled': bool(self.settings.get('enabled')), 'configured': bool(self.settings.get('token')),
                'chat_id': self.settings.get('chat_id'), 'bot_username': self.settings.get('bot_username'),
                'last_test_at': self.settings.get('last_test_at'),
                'note': 'Only new, recent SSH findings are sent. Historical imports, demo mode, controlled tests and expected activity stay in the inbox.'}

    def _save(self, settings):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = self.path.with_name(f'.telegram-{uuid4().hex}.tmp')
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(settings, f)
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)
        self.settings = settings

    async def configure(self, token, chat_id, consent):
        if not consent:
            raise ValueError('Consent is required to send alert summaries to Telegram.')
        if not re.fullmatch(r'[0-9]{5,20}:[A-Za-z0-9_-]{20,100}', token or ''):
            raise ValueError('Enter a valid Telegram bot token.')
        if not re.fullmatch(r'[1-9][0-9]{0,18}', chat_id or ''):
            raise ValueError('Enter your positive numeric private chat ID, not a group or channel.')
        async with self.lock:
            if now_ms() - self.last_setup < 10_000:
                raise ValueError('Wait ten seconds before trying again.')
            self.last_setup = now_ms()
            bot = await telegram_call(token, 'getMe', {})
            chat = await telegram_call(token, 'getChat', {'chat_id': chat_id})
            if chat.get('type') != 'private' or str(chat.get('id')) != chat_id or not bot.get('is_bot'):
                raise ValueError('Only a private chat with your bot is supported. Start the bot in Telegram first.')
            self._save({'token': token, 'chat_id': chat_id, 'bot_username': bot.get('username'),
                        'enabled': True, 'consented_at': now_ms()})
            # Never move an existing queue to a newly configured recipient.
            self.repo.con.execute("UPDATE security_alerts SET delivery='cancelled' WHERE delivery='pending'")
        return self.status()

    async def disable(self):
        async with self.lock:
            self._save({})  # Forget the token, not just the enabled flag.
            self.repo.con.execute("UPDATE security_alerts SET delivery='cancelled' WHERE delivery='pending'")
        return self.status()

    async def test(self):
        async with self.lock:
            if not self.settings.get('enabled'):
                raise ValueError('Configure Telegram first.')
            if now_ms() - self.settings.get('last_test_at', 0) < 30_000:
                raise ValueError('Wait thirty seconds before another test.')
            self._save({**self.settings, 'last_test_at': now_ms()})
            await telegram_call(self.settings['token'], 'sendMessage', {
                'chat_id': self.settings['chat_id'], 'text': 'ANVAYA test notification. No incident or attack is implied.',
                'protect_content': True, 'link_preview_options': {'is_disabled': True}})
        return {'ok': True}

    def record(self, summary, stages):
        failures = [e for e in stages.get('credential', []) if e.get('format') == 'openssh-journal']
        failures = list({(e['device'], e['src_ip'], e.get('src_port')): e for e in failures}.values())
        counts = Counter(e['device'] for e in failures)
        failures = [e for e in failures if counts[e['device']] >= 10]
        if not failures:
            return
        successes = [e for e in stages.get('access', []) if e.get('format') == 'openssh-journal' and e['status'] == 'Success']
        kinds = [('ssh_failures', failures)] + ([('ssh_success_after_failures', successes)] if successes else [])
        for kind, evidence in kinds:
            at = now_ms()
            event_at = max(e['time'] for e in evidence)
            historical = not (at - 10 * 60_000 <= event_at <= at + 60_000)
            workflow = summary.get('workflow', {})
            suppressed = (self.c.cfg.demo_mode or workflow.get('controlled_test')
                          or workflow.get('assessment') == 'expected'
                          or any(str(e['device']).lower().startswith('synthetic-lab-') for e in failures))
            delivery = ('historical' if historical else 'suppressed' if suppressed else
                        'pending' if self.settings.get('enabled') else 'disabled')
            payload = {'title': 'SSH login after repeated failures' if successes and kind != 'ssh_failures' else 'Repeated SSH login failures',
                       'source_ip': summary['attacker_ip'], 'devices': list(dict.fromkeys(e['device'] for e in evidence)),
                       'level': 'High' if kind != 'ssh_failures' else 'Medium', 'failure_count': len(failures),
                       'event_ids': [e['event_id'] for e in evidence[:50]], 'evidence_count': len(evidence),
                       'controlled_test': bool(workflow.get('controlled_test')), 'demo': self.c.cfg.demo_mode,
                       'assessment': workflow.get('assessment', 'unreviewed')}
            cursor = self.repo.con.execute(
                'INSERT OR IGNORE INTO security_alerts(incident_id,kind,created_at,event_time,payload,historical,delivery) VALUES (?,?,?,?,?,?,?)',
                (summary['incident_id'], kind, at, event_at, json.dumps(payload), int(historical), delivery))
            if cursor.rowcount:
                self.c.publish('alert.created', {'id': cursor.lastrowid, 'incident_id': summary['incident_id']})

    def listing(self, before=None):
        rows = self.repo.con.execute('SELECT * FROM security_alerts WHERE (? IS NULL OR id < ?) ORDER BY id DESC LIMIT 51',
                                     (before, before)).fetchall()
        items = [{**dict(row), 'payload': json.loads(row['payload']), 'historical': bool(row['historical'])} for row in rows[:50]]
        unread = self.repo.con.execute('SELECT COUNT(*) FROM security_alerts WHERE seen_at IS NULL').fetchone()[0]
        return {'items': items, 'unread': unread, 'next_before': items[-1]['id'] if len(rows) > 50 else None}

    def acknowledge(self, alert_id):
        cursor = self.repo.con.execute('UPDATE security_alerts SET seen_at=COALESCE(seen_at,?) WHERE id=?', (now_ms(), alert_id))
        if not cursor.rowcount:
            raise KeyError(alert_id)

    async def tick(self):
        async with self.lock:
            if not self.settings.get('enabled') or self.c.cfg.demo_mode:
                return
            at = now_ms()
            last = self.repo.get_meta('telegram_last_attempt') or 0
            if at - last < 10_000:
                return
            row = self.repo.con.execute("SELECT * FROM security_alerts WHERE delivery='pending' AND next_attempt<=? ORDER BY id LIMIT 1", (at,)).fetchone()
            if not row:
                return
            inc = self.repo.incident_summary(row['incident_id'])
            workflow = inc.get('workflow', {}) if inc else {}
            if not inc or workflow.get('controlled_test') or workflow.get('assessment') == 'expected':
                self.repo.con.execute("UPDATE security_alerts SET delivery='suppressed' WHERE id=?", (row['id'],))
                return
            if at - row['event_time'] > 15 * 60_000:
                self.repo.con.execute("UPDATE security_alerts SET delivery='expired' WHERE id=?", (row['id'],))
                return
            payload = json.loads(row['payload'])
            event_time = datetime.fromtimestamp(row['event_time'] / 1000, timezone.utc).isoformat()
            text = (f"ANVAYA | {payload['level']} | {payload['title']}\n"
                    f"Source: {payload['source_ip']}\nDevices: {', '.join(payload['devices'])[:300]}\n"
                    f"Failed connections: {payload['failure_count']}\nEvent time: {event_time}\n"
                    f"Incident: {row['incident_id']}\nReview whether the activity was authorized. No automatic blocking occurred.")
            if self.c.cfg.public_origin.startswith('https://'):
                text += f"\n{self.c.cfg.public_origin}/incidents/{row['incident_id']}"
            attempts = row['attempts'] + 1
            self.repo.set_meta('telegram_last_attempt', at)
            self.repo.con.execute('UPDATE security_alerts SET attempts=?,next_attempt=? WHERE id=?',
                                  (attempts, at + 30_000, row['id']))
            try:
                await telegram_call(self.settings['token'], 'sendMessage', {'chat_id': self.settings['chat_id'],
                    'text': text[:4000], 'protect_content': True, 'link_preview_options': {'is_disabled': True}})
                self.repo.con.execute("UPDATE security_alerts SET delivery='sent',sent_at=?,last_error=NULL WHERE id=?", (now_ms(), row['id']))
            except TelegramError as error:
                terminal = attempts >= 5 or error.code == 'destination_rejected'
                delay = max(30 * 2 ** (attempts - 1), error.retry_after)
                self.repo.con.execute('UPDATE security_alerts SET delivery=?,last_error=?,next_attempt=? WHERE id=?',
                    ('failed' if terminal else 'pending', error.code, now_ms() + delay * 1000, row['id']))

    async def run(self):
        while True:
            await self.tick()
            await asyncio.sleep(5)
