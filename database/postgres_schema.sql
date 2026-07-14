-- ============================================================
--  Valve Diagnostic Tool POC — Postgres data store
--  One table, long format: one row per (tag, timestamp).
--  tag_name is the EXACT Excel Sheet1 column name
--  (e.g. YN.ETH1.15FC311_PV) so the DB round-trips cleanly
--  back into the same wide format the engine already expects.
-- ============================================================

CREATE TABLE IF NOT EXISTS tag_readings (
    id          BIGSERIAL PRIMARY KEY,
    tag_name    TEXT             NOT NULL,
    ts          TIMESTAMP        NOT NULL,
    value       DOUBLE PRECISION,
    text_value  TEXT,                        -- for MODE columns (AUTO/MAN/etc, not numeric)
    source_file TEXT,                        -- original Excel filename, for audit/debug
    uploaded_by TEXT,                        -- user email
    uploaded_at TIMESTAMP        NOT NULL DEFAULT now(),
    CONSTRAINT uq_tag_ts UNIQUE (tag_name, ts)
);

CREATE INDEX IF NOT EXISTS ix_tag_readings_tag_ts ON tag_readings (tag_name, ts);
CREATE INDEX IF NOT EXISTS ix_tag_readings_ts     ON tag_readings (ts);

-- Upsert behaviour: re-uploading a file with overlapping timestamps
-- just overwrites those rows (ON CONFLICT DO UPDATE), so repeat
-- uploads of the same period are idempotent.


-- ============================================================
--  loop_summary — fast lookup for the Database tab's loop picker.
--  One row per loop, kept in sync on every insert. Without this,
--  listing available loops means scanning every row in tag_readings
--  just to find distinct tag names — fine at 57K rows, gets slower
--  as more uploads accumulate. This makes that lookup a fast,
--  index-covered read regardless of table size.
-- ============================================================
CREATE TABLE IF NOT EXISTS loop_summary (
    loop_name     TEXT      PRIMARY KEY,
    reading_count BIGINT    NOT NULL DEFAULT 0,
    min_ts        TIMESTAMP,
    max_ts        TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT now()
);
