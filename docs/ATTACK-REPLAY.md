# Attack Replay

Open **Attack Replay** in the navigation, choose an incident, and press **Play
replay**. Incident pages also link to their replay. A link such as
`/replay?incident=inc-0003` selects an incident within the signed-in workspace.

The schematic connects recorded source addresses to reporting devices. It is not
a physical network map or proof that an attacker moved between those devices.
Select a node, connection, stage, or sequence event to inspect the corresponding
record. **Inspect raw evidence** leads to the event page and its integrity tools.
The replay itself does not verify cryptographic proofs or change any logs.

Playback starts paused. Play/pause, restart, previous/next, speed, and the position
slider operate on the chronological event sequence. Original timestamps stay
visible. At 1×, playback advances one event per second; gaps between source events
are compressed. Events with identical timestamps are ordered by ingestion sequence
and identifier. Reduced-motion preferences suppress signal movement.

The page freezes the loaded incident for playback. **Reload** fetches a new
snapshot and restarts from the beginning, so newly arriving evidence cannot shift
the sequence midway through a replay. It is recorded-event playback, not a live
attack stream.

At most the earliest 500 valid-timestamp events are replayed, with any omissions
explicitly disclosed. The graph bounds visible source/device nodes and always
includes the selected event's endpoints. The evidence sequence remains available
for navigating other records. Missing addresses are not invented.

**Controlled test** comes from the incident's analyst annotation. Devices named
`synthetic-lab-*` are labelled as synthetic-labelled sources; demo mode is shown
separately. These labels are not independent provenance verification, and an
unlabelled incident is not proof of a real attack. The page uses the same
authenticated, account-isolated incident API as the investigation view, sends
nothing to an AI provider, and generates no events.
