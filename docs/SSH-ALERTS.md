# SSH alerts and Telegram setup

ANVAYA flags ten distinct failed SSH connections from one IP to one device in a
10-minute correlation window. Multiple messages for the same source port count
once. Windows are anchored to stored events, not a continuously sliding window;
slow attempts or attempts split across windows may not meet this rule.

A successful SSH login from the same IP to the same device after the threshold,
and within 15 minutes of the last failure, raises the finding from Medium (40)
to High (75). A shared IP or legitimate retry can explain this: review the
evidence and account owner before deciding it is malicious. This is a fixed
detection rule, not an AI verdict. Missing logs can mean missing detections.

## Connect your private Telegram chat

1. In Telegram, open the official **@BotFather** and send `/newbot`. Follow its
   instructions and save the token privately. Use a dedicated ANVAYA bot.
2. Open your new bot and press **Start**.
3. From PowerShell in the ANAVYA project folder, run:

   ```powershell
   .\.venv\Scripts\python.exe .\collectors\telegram_chat.py
   ```

   Paste the token into the hidden prompt, not into the command line or an AI
   chat. The helper prints private chat IDs only, does not save the token,
   and does not change a webhook or acknowledge updates with an offset.
   If multiple IDs appear, use a dedicated bot only you have started.
4. Sign in to ANVAYA and open **Alert inbox**. Enter the token and your private
   chat ID, review the data-sharing checkbox, and select **Connect Telegram**.
5. Select **Send test message** and check your private Telegram chat.

Official instructions: [Telegram bot tutorial](https://core.telegram.org/bots/tutorial#obtain-your-bot-token).

## What is sent and stored

Alerts contain the finding title, source IP, device names, failed-connection
count, event time, incident ID and an HTTPS incident link when configured.
They do not include raw logs, analyst notes, passwords or AI explanations.
Telegram receives those summaries. The server stores the bot token in a
private per-workspace file; the server operator can access it. Keep server
backups private because they can contain saved tokens. Disconnecting clears
the active token and cancels pending messages; it cannot erase Telegram
messages or old server backups. Revoke a compromised token with BotFather.

Each workspace has a separate inbox and connection. The app accepts private
chats only. Configuration validates the bot and chat, but cannot prove a
Telegram identity belongs to a particular ANVAYA username.

## Delivery and review

- New eligible findings generate one failure alert and at most one
  success-after-failure escalation per incident. Replaying the same finding
  does not create another alert.
- Only event timestamps within the previous ten minutes (with one minute of
  future clock tolerance) are queued. Historical imports remain visible in the
  inbox. Existing incidents are not automatically backfilled on installation.
- Demo mode, synthetic-lab device names, controlled tests and expected activity
  suppress automatic delivery. The explicit test button still sends a clearly
  labelled test message. Marking an incident expected suppresses its pending
  messages, not every future finding from that IP.
- Delivery runs every five seconds, with at least ten seconds between attempts
  per workspace. Transient errors retry with backoff, up to five attempts;
  destination errors stop immediately. Messages expire 15 minutes after the
  event. Network timeouts can cause duplicate delivery if Telegram accepted a
  request before the response was lost. “Accepted by Telegram” is not a read
  receipt. Inspect delivery status in the inbox.
- Review the evidence and nearby successful logins, select **Expected activity**
  or **Suspicious**, add a note, and save. Marking an alert read does not resolve
  the incident. No traffic is blocked and no server settings are changed.

Keep the real SSH collector running for timely alerts. Importing yesterday's
logs demonstrates detection and investigation, but deliberately does not send
old findings to Telegram. Do not weaken your EC2 firewall to generate alerts.
