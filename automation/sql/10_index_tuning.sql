-- =============================================================================
-- 10_index_tuning.sql - indexes chosen from the query plans of the SQL retriever
-- (run once; re-runnable). bench/sql_tuning.py prints EXPLAIN and timings for the
-- same queries with and without these indexes.
--
--   idx_serial      equipment_units(serial_number)
--       Every unit question runs "WHERE equipment_id = ? OR serial_number = ?".
--       serial_number had no index, so the OR forced a scan of all 2,500 units.
--       With the index MariaDB merges two index lookups (index_merge / union).
--
--   idx_equip_date  rag_payloads(equipment_id, event_date)
--       A unit's history is "WHERE equipment_id = ? ORDER BY event_date DESC LIMIT n",
--       and a temporal question adds a date range. The single-column idx_equip found
--       the rows but still sorted them (filesort); the composite index returns them
--       already in date order and serves the range. idx_equip becomes redundant
--       (it is a prefix of the new index), so it is dropped to save write cost.
--
-- Not indexed, on purpose: parts_inventory.part_name is searched with LIKE '%term%',
-- which no B-tree index can serve; the table has 150 rows, so a scan costs microseconds.
-- =============================================================================
USE gigavolt_erp;

CREATE INDEX IF NOT EXISTS idx_serial     ON equipment_units (serial_number);
CREATE INDEX IF NOT EXISTS idx_equip_date ON rag_payloads (equipment_id, event_date);
DROP INDEX IF EXISTS idx_equip ON rag_payloads;

ANALYZE TABLE equipment_units, rag_payloads, service_logs, warranty_claims;
