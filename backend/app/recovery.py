"""Password recovery using hashed, single-use offline codes."""
import hmac
import secrets

from app.api.errors import ApiError
from app.auth import digest, password_hash


class Recovery:
    def __init__(self, accounts):
        self.accounts, self.con = accounts, accounts.con
        self.con.executescript('''
            CREATE TABLE IF NOT EXISTS recovery_settings (
                account_id TEXT PRIMARY KEY, code_hash TEXT);
        ''')

    def profile(self, account_id):
        row = self.con.execute('SELECT * FROM recovery_settings WHERE account_id=?', (account_id,)).fetchone()
        return {'has_recovery_code': bool(row and row['code_hash'])}

    def verify_password(self, account_id, password):
        row = self.accounts.by_id(account_id)
        if not row or not hmac.compare_digest(password_hash(password, row['salt']), row['password_hash']):
            raise ApiError(400, 'invalid_password', 'Current password is incorrect.')

    def issue_code(self, account_id):
        code = secrets.token_urlsafe(32)
        with self.con:
            self.con.execute('''INSERT INTO recovery_settings(account_id,code_hash) VALUES (?,?)
                ON CONFLICT(account_id) DO UPDATE SET code_hash=excluded.code_hash''', (account_id, digest(code)))
        return code

    def reset(self, username, code, password):
        if not 12 <= len(password) <= 1024:
            raise ApiError(422, 'validation_error', 'Use a password of 12–1024 characters.')
        row = self.con.execute('''SELECT a.* FROM accounts a JOIN recovery_settings r ON r.account_id=a.id
            WHERE a.username=? COLLATE NOCASE AND r.code_hash=? AND a.disabled=0''',
            (username, digest(code.strip()))).fetchone() if code else None
        if not row:
            raise ApiError(400, 'invalid_recovery', 'The recovery details are invalid, expired or already used.')
        salt = secrets.token_hex(16)
        hashed = password_hash(password, salt)
        # Synchronous transaction: no await between validating and consuming the proof.
        with self.con:
            self.con.execute('UPDATE accounts SET salt=?,password_hash=? WHERE id=?', (salt, hashed, row['id']))
            self.con.execute('UPDATE recovery_settings SET code_hash=NULL WHERE account_id=?', (row['id'],))
        return row['id']
