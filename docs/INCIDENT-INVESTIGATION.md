# Incident investigations

Open an incident and use **Investigation** to choose New, Investigating, or
Resolved, add a note, and optionally mark it as a Controlled test. Click **Save
investigation**. The list and incident header show the saved state and label.

Notes are plain text, limited to 5,000 characters per update, and append-only in
the application. Activity shows the latest 100 updates with author and local
display time. Older entries remain stored. Status and label changes also create
an activity entry, even if no note is supplied.

Resolved incidents stay visible, but no longer count as open on the overview.
Changing one back to New or Investigating reopens it. Correlation updates preserve
the chosen state; additional matching evidence does not automatically reopen a
resolved incident. Review its timeline when reopening it.

Investigation data belongs to the signed-in account's workspace. It is stored
separately from raw logs, normalized events, and integrity proofs. Activity is
ordinary application metadata, not part of the cryptographic evidence ledger.
Marking a Controlled test does not change the detection score or original logs.

If another tab saves first, the older update is rejected. Use **Load latest
status; keep my note**, review the latest status and label, then save again.

Existing databases receive additive workflow/activity tables at startup; existing
open incidents appear as New, and closed incidents as Resolved. The existing
open/closed status remains synchronized for statistics and compatibility.
