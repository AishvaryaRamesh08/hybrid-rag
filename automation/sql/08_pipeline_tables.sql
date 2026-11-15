-- =============================================================================
-- 08_pipeline_tables.sql - state for the automated pipeline (run once; re-runnable).
--
--   batch_*            working copy of ONE incoming ERP batch. The Bronze tables
--                      (import_*) stay the append-only raw history; a batch is only
--                      appended to them after it has been validated and merged.
--   etl_file_manifest  every landing file seen, with its SHA-256 hash, so a file is
--                      processed once and a changed file is processed again
--   etl_runs           one row per pipeline run, with its status and summary
--   etl_task_runs      one row per task per run: status, timing, attempts, row counts
--   etl_quarantine     rows that failed validation, kept with the reason, not loaded
--   etl_state          small key/value flags that must survive a crash
--                      (for example "rag_payloads must be rebuilt")
--   rag_vector_sync    what the vector store holds for each rag_payloads row (a hash
--                      of its text and metadata). Comparing it with rag_payloads
--                      tells the pipeline exactly which rows to embed or delete.
-- =============================================================================
USE gigavolt_erp;

CREATE TABLE IF NOT EXISTS batch_customers       LIKE import_customers;
CREATE TABLE IF NOT EXISTS batch_equipment       LIKE import_equipment;
CREATE TABLE IF NOT EXISTS batch_dispatches      LIKE import_dispatches;
CREATE TABLE IF NOT EXISTS batch_parts           LIKE import_parts;
CREATE TABLE IF NOT EXISTS batch_warranty_claims LIKE import_warranty_claims;

CREATE TABLE IF NOT EXISTS etl_runs (
  run_id       VARCHAR(40)  PRIMARY KEY,
  started_at   DATETIME(3)  NOT NULL,
  finished_at  DATETIME(3),
  status       VARCHAR(20)  NOT NULL,          -- running | success | failed | no_changes
  trigger_type VARCHAR(20)  NOT NULL,          -- manual | watch | timer
  summary      JSON
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS etl_task_runs (
  run_id      VARCHAR(40)  NOT NULL,
  task        VARCHAR(60)  NOT NULL,
  status      VARCHAR(20)  NOT NULL,           -- success | skipped | failed | blocked
  started_at  DATETIME(3),
  duration_ms INT,
  attempts    INT,
  rows_in     INT,
  rows_out    INT,
  message     VARCHAR(1000),
  PRIMARY KEY (run_id, task)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS etl_file_manifest (
  file_path    VARCHAR(500) NOT NULL,
  sha256       CHAR(64)     NOT NULL,
  source_type  VARCHAR(20)  NOT NULL,          -- erp | telemetry | document
  size_bytes   BIGINT,
  first_seen   DATETIME(3)  NOT NULL,
  processed_at DATETIME(3),
  run_id       VARCHAR(40),
  status       VARCHAR(20)  NOT NULL,          -- pending | processed | failed | rejected
  attempts     INT          NOT NULL DEFAULT 0,
  rows_loaded  INT,
  PRIMARY KEY (file_path, sha256)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS etl_quarantine (
  quarantine_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id        VARCHAR(40)  NOT NULL,
  source_type   VARCHAR(20)  NOT NULL,
  source_file   VARCHAR(500),
  record_key    VARCHAR(100),
  reason        VARCHAR(255) NOT NULL,
  raw_record    JSON,
  created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY idx_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS etl_state (
  state_key   VARCHAR(60)  PRIMARY KEY,
  state_value VARCHAR(255) NOT NULL,
  updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rag_vector_sync (
  source_table VARCHAR(50) NOT NULL,
  source_id    VARCHAR(50) NOT NULL,
  content_hash CHAR(64)    NOT NULL,           -- SHA-256 of payload_text + metadata
  part_count   INT         NOT NULL,           -- vectors stored for this payload
  synced_at    DATETIME(3) NOT NULL,
  run_id       VARCHAR(40),
  PRIMARY KEY (source_table, source_id)
) ENGINE=InnoDB;
