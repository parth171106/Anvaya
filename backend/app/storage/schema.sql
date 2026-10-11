CREATE TABLE raw_events (
  seq              INTEGER PRIMARY KEY,                -- monotonic from 1
  raw_id           TEXT    NOT NULL UNIQUE,
  raw_sha256       TEXT    NOT NULL,                   -- over the exact received bytes
  size             INTEGER NOT NULL CHECK (size >= 0),
  segment          TEXT    NOT NULL,                   -- 'seg-000001.log'
  offset           INTEGER NOT NULL,                   -- byte offset of the u32 length prefix
  encoding         TEXT    NOT NULL CHECK (encoding IN ('utf-8','binary')),
  flags            TEXT    NOT NULL DEFAULT '[]',      -- JSON array of vetting flags
  transport        TEXT    NOT NULL CHECK (transport IN ('udp','tcp','http','file')),
  peer_ip          TEXT    NOT NULL,
  received_at      INTEGER NOT NULL,                   -- Clock.now_ms() at receipt
  wall_received_at INTEGER NOT NULL,                   -- real wall clock (for silence detection)
  status           TEXT    NOT NULL CHECK (status IN ('pending','parsed','quarantined')),
  batch_id         INTEGER REFERENCES ledger_batches(batch_id)
);
CREATE INDEX ix_raw_status ON raw_events(status);
CREATE INDEX ix_raw_batch  ON raw_events(batch_id);

CREATE TABLE events (
  event_id          TEXT    PRIMARY KEY,
  raw_id            TEXT    NOT NULL UNIQUE REFERENCES raw_events(raw_id),
  seq               INTEGER NOT NULL,
  time              INTEGER NOT NULL,                  -- OCSF time (epoch ms UTC)
  device            TEXT    NOT NULL,                  -- fw01 | ids01 | vpn01 | br01
  vendor            TEXT    NOT NULL,                  -- Cisco | OISF | Fortinet | Acme
  product           TEXT    NOT NULL,                  -- ASA | Suricata | FortiGate | EdgeRouter
  format            TEXT    NOT NULL,                  -- cisco-asa-syslog | suricata-eve-json | fortigate-kv | acme-edge-pipe
  class_uid         INTEGER NOT NULL CHECK (class_uid IN (4001,2004,3002)),
  class_name        TEXT    NOT NULL,
  activity_name     TEXT    NOT NULL,                  -- Open | Close | Refuse | Traffic | Create | Logon
  src_ip            TEXT,                              -- 4001/3002: src_endpoint.ip · 2004: evidences[0].src_endpoint.ip
  src_port          INTEGER,
  dst_ip            TEXT,
  dst_port          INTEGER,
  protocol          TEXT,                              -- connection_info.protocol_name (lower case)
  direction         TEXT,                              -- Inbound | Outbound | NULL
  user_name         TEXT,
  action            TEXT CHECK (action IN ('Allowed','Denied') OR action IS NULL),
  status            TEXT CHECK (status IN ('Success','Failure') OR status IS NULL),
  severity          TEXT    NOT NULL,                  -- Informational | Low | Medium | High | Critical
  title             TEXT,                              -- 2004: finding_info.title · else NULL
  parse_confidence  INTEGER NOT NULL CHECK (parse_confidence BETWEEN 0 AND 100),
  parser            TEXT    NOT NULL,                  -- 'cisco-asa@1.0.0'
  rule_id           TEXT    NOT NULL,
  roundtrip_ok      INTEGER NOT NULL CHECK (roundtrip_ok IN (0,1)),
  roundtrip_coverage REAL   NOT NULL,
  ocsf_json         TEXT    NOT NULL,                  -- the OCSF object (§4)
  anvaya_json       TEXT    NOT NULL                   -- the anvaya object (§4)
);
CREATE INDEX ix_events_time   ON events(time DESC);
CREATE INDEX ix_events_src    ON events(src_ip);
CREATE INDEX ix_events_dst    ON events(dst_ip);
CREATE INDEX ix_events_device ON events(device, time DESC);
CREATE INDEX ix_events_class  ON events(class_uid, status, action);

CREATE TABLE ledger_batches (
  batch_id     INTEGER PRIMARY KEY,                    -- 1, 2, 3 …
  first_seq    INTEGER NOT NULL,
  last_seq     INTEGER NOT NULL,
  leaf_count   INTEGER NOT NULL CHECK (leaf_count BETWEEN 1 AND 16),
  merkle_root  TEXT    NOT NULL,
  prev_head    TEXT    NOT NULL,                       -- 64 zeros for batch 1
  head         TEXT    NOT NULL,
  signature    TEXT    NOT NULL,                       -- Ed25519 over head
  pubkey_fp    TEXT    NOT NULL,                       -- primary key fingerprint (16 hex)
  sealed_at    INTEGER NOT NULL,
  resealed     INTEGER NOT NULL DEFAULT 0 CHECK (resealed IN (0,1)),   -- set by demo reseal only
  CHECK (last_seq >= first_seq)
);

CREATE TABLE witness_signatures (
  batch_id     INTEGER NOT NULL REFERENCES ledger_batches(batch_id),
  witness      TEXT    NOT NULL CHECK (witness IN ('witness-ntro','witness-certin')),
  status       TEXT    NOT NULL CHECK (status IN ('cosigned','rejected')),
  head         TEXT    NOT NULL,                       -- head as sent at co-sign time
  cosignature  TEXT,                                   -- NULL if rejected
  reason       TEXT,                                   -- rejection reason
  cosigned_at  INTEGER NOT NULL,
  PRIMARY KEY (batch_id, witness)
);

CREATE TABLE sources (
  device          TEXT    PRIMARY KEY,
  vendor          TEXT    NOT NULL,
  product         TEXT    NOT NULL,
  format          TEXT    NOT NULL,
  parser          TEXT    NOT NULL,
  first_seen      INTEGER NOT NULL,                    -- Clock ms
  last_seen       INTEGER NOT NULL,                    -- Clock ms
  first_seen_wall INTEGER NOT NULL,                    -- real ms
  last_seen_wall  INTEGER NOT NULL,                    -- real ms
  events_total    INTEGER NOT NULL DEFAULT 0,
  expected_gap_s  REAL,                                -- median of the last 20 real gaps
  status          TEXT    NOT NULL DEFAULT 'learning' CHECK (status IN ('learning','active','silent'))
);

CREATE TABLE parsers (
  name          TEXT NOT NULL,
  version       TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('active','retired')),
  origin        TEXT NOT NULL CHECK (origin IN ('builtin','ai_draft','user')),
  format        TEXT NOT NULL,
  priority      INTEGER NOT NULL,
  yaml          TEXT NOT NULL,
  yaml_sha256   TEXT NOT NULL,
  approved_by   TEXT,
  approved_at   INTEGER,
  PRIMARY KEY (name, version)
);

CREATE TABLE parser_drafts (
  draft_id         TEXT PRIMARY KEY,
  group_id         TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('drafted','tested','approved','rejected')),
  origin           TEXT NOT NULL CHECK (origin IN ('llm_live','llm_cached','hand_authored')),
  model            TEXT,
  generated_at     INTEGER,
  yaml             TEXT NOT NULL,
  holdout_indexes  TEXT NOT NULL,                      -- JSON array, e.g. [2,5,8,11,14,17]
  test_result      TEXT,                               -- JSON (TRD.md API 17)
  promotable       INTEGER NOT NULL DEFAULT 0 CHECK (promotable IN (0,1)),
  decided_by       TEXT,
  decided_at       INTEGER,
  reject_reason    TEXT,
  created_at       INTEGER NOT NULL,
  UNIQUE (group_id, status)                            -- one open draft per group in practice
);

CREATE TABLE quarantine (
  raw_id          TEXT PRIMARY KEY REFERENCES raw_events(raw_id),
  group_id        TEXT NOT NULL,
  shape_signature TEXT NOT NULL,                       -- 'EDGE|x12'
  reason          TEXT NOT NULL CHECK (reason IN ('no_fingerprint','no_rule','parse_error','schema_invalid','roundtrip_fail')),
  detail          TEXT,
  first_seen      INTEGER NOT NULL
);
CREATE INDEX ix_quarantine_group ON quarantine(group_id);

CREATE TABLE incidents (
  incident_id    TEXT PRIMARY KEY,
  attacker_ip    TEXT NOT NULL,
  target_ip      TEXT,
  window_start   INTEGER NOT NULL,
  title          TEXT NOT NULL,
  stages         TEXT NOT NULL,                        -- JSON array in order: ["recon","credential","access"]
  devices        TEXT NOT NULL,                        -- JSON array
  risk           INTEGER NOT NULL CHECK (risk BETWEEN 0 AND 100),
  level          TEXT NOT NULL CHECK (level IN ('Low','Medium','High')),
  risk_breakdown TEXT NOT NULL,                        -- JSON {"stages":75,"devices":10,"ordered":10}
  first_time     INTEGER NOT NULL,
  last_time      INTEGER NOT NULL,
  status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  UNIQUE (attacker_ip, window_start)
);

CREATE TABLE incident_events (
  incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
  event_id    TEXT NOT NULL REFERENCES events(event_id),
  stage       TEXT NOT NULL CHECK (stage IN ('recon','credential','access')),
  PRIMARY KEY (incident_id, event_id)
);

CREATE TABLE audit_log (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  at      INTEGER NOT NULL,
  actor   TEXT    NOT NULL,                            -- 'system' | 'presenter' | 'analyst@ntro-demo'
  action  TEXT    NOT NULL,                            -- 'parser.approve' | 'parser.reject' | 'search.ask' | 'demo.tamper' | 'demo.reseal' | 'demo.reset' | 'export.parquet'
  object  TEXT,
  detail  TEXT    NOT NULL DEFAULT '{}'
);
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT,'audit_log is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT,'audit_log is append-only'); END;

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,                              -- 'last_verify' | 'ocsf_version' | 'schema_version' | 'demo_state'
  value TEXT NOT NULL
);
