# EC2 SSH live collection demonstration — 15 October 2026

This was a controlled test on the project owner's EC2 instance. The events are
real OpenSSH journal records caused by intentionally rejected connections, not
evidence of an actual attack. No raw records were edited to label the test.

## Verified results

- The existing `anvaya-ssh` service was already collecting continuously. Its key
  targets the active owner/admin workspace. No second collector was installed.
- A service restart completed successfully; delivery resumed using its existing
  checkpoint. The service remained running, enabled at boot, with no automatic
  restarts reported after the check. This was a service restart test, not a VM
  reboot or network-outage test.
- Exactly ten separate connections used an untrusted temporary key and the
  nonexistent username `anvaya-check-20261015`. All were rejected. Password
  authentication and the restricted SSH firewall rule were left unchanged.
- ANVAYA stored ten `openssh-journal` events with ten distinct source ports on
  device `ip-172-31-23-120`. All ten passed round-trip validation.
- The correlation engine created **`inc-0003`**, **Repeated SSH login failures**,
  with severity **Medium** and risk **40/100**, linked to the test events.
- Read-only verification checked all ten raw hashes, their Merkle roots in
  batches **62, 64, 65, 66, 67, 68**, and the signed head chain through batch 68.
  Both local witness stores matched, and their signatures verified. These are
  simulated witnesses on the same deployment, not independent external agencies.

## Inspect it in the app

Use the deployed app and sign into the admin account that receives the EC2
collector's events. The separate local demonstration has different data.

1. Open **Incidents**, then `inc-0003` (Repeated SSH login failures).
2. Inspect the linked events: device `ip-172-31-23-120`, username
   `anvaya-check-20261015`, failed authentication, and ten different source ports.
3. Open a linked event's raw evidence and integrity proof. The preserved log,
   normalized fields, and proof should refer to the same record.
4. For a wider view, search for **Show SSH logs**. If the test has aged out of a
   time filter, include 15 October 2026 or select all dates.

This verifies the path from server journal → continuous collector → authenticated
ingestion → normalization → correlation → sealed evidence. It does not test every
parser, multiple-source attack correlation, remote independent witnesses, or AI
explanations. No evidence was sent to an AI provider during this test.

Installation and operational details: [Linux SSH collection](LINUX-SSH.md).
