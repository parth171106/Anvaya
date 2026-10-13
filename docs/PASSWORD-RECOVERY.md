# Password visibility and recovery

Password fields have independent Show/Hide controls and start hidden.
Password recovery uses saved codes only; no email service is required.

New accounts receive a 256-bit recovery code once, before sign-in. Existing users
open Account, confirm their current password and generate a code. Save it in a
password manager or another private place: it grants password-reset access.
The server stores only its SHA-256 hash. Replacing a code revokes the old one.

Use Forgot password on the sign-in page and enter your username, saved code and
new password (12–1024 characters). A successful reset consumes the code, creates
a fresh password salt/hash and ends that account's browser sessions, including
event streams. It does not automatically sign you in, delete logs or replace
collector keys. After signing in, generate and save a new code from Account.
Codes remain valid until replaced or consumed, including across server restarts.

Recovery cannot work with a username or support email alone. If you lose both
your password and recovery code, there is no self-service recovery path.
The application has no public administrator override or collector-key reset path.

Recovery requests require same-origin console headers, bounded input and rate
limiting. Tests use isolated synthetic accounts to check single use, rotation,
session revocation, disabled accounts, persistence and rejection of invalid input.
