-- =============================================================================
-- 11_cdc_triggers.sql - trigger-based change data capture (CDC). Run once; re-runnable.
--
-- Why: the pipeline already detects new FILES. This catches changes made DIRECTLY in
-- MariaDB (an application or a person running INSERT / UPDATE / DELETE), which no file
-- announces. Without it, the RAG text, vectors and cached answers would keep the old values.
--
-- How:
--   * Every insert, update and delete on the seven Silver tables that feed the RAG text
--     writes one row to Audit_Logs, the immutable audit table from Milestone 2.
--     So Audit_Logs is both the compliance audit trail and the change feed.
--   * change_source records WHO made the change: the pipeline sets the session variable
--     @etl_run_id before it merges a batch, so its own writes are tagged with the run ID.
--     Everything else is tagged 'direct'. The pipeline's cdc_detect task reads only the
--     'direct' rows, so it never reacts to its own writes.
--   * An UPDATE that changes nothing writes nothing. The merge "updates" every unchanged
--     row of a batch, so this removes most of the trigger cost and all of the noise.
--
-- Changes from the Milestone 2 triggers (m2_trigger.sql):
--   * DELETE is captured, and parts_inventory, equipment_models and locations are covered
--   * snapshots hold the whole row, not a selection of columns
--   * changed_by uses USER() (the connected client). M2 used CURRENT_USER(), which inside a
--     trigger returns the trigger's DEFINER, so every row showed the same administrator.
--
-- Known limit: MariaDB does not fire triggers for rows removed by a foreign-key cascade
-- (deleting a unit cascades to its warranty claims). The unit's own DELETE is still captured,
-- and the payload refresh rebuilds every payload, so the cascaded rows disappear too.
--
-- Order on a new instance: load the data first (M1), then run this file, so the initial
-- bulk load is not written to the audit log.
-- =============================================================================
USE gigavolt_erp;

-- The Milestone 2 table, created only if this instance does not have it yet
CREATE TABLE IF NOT EXISTS Audit_Logs (
  audit_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  changed_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  changed_by      VARCHAR(128),
  table_name      VARCHAR(64)  NOT NULL,
  operation_type  VARCHAR(10)  NOT NULL,
  record_id       VARCHAR(50),
  old_values      JSON,
  new_values      JSON,
  change_desc     VARCHAR(255),
  KEY idx_table_op  (table_name, operation_type),
  KEY idx_record    (record_id),
  KEY idx_changed_at(changed_at)
) ENGINE=InnoDB;

-- New in Milestone 6: who made the change ('direct', or the pipeline run ID)
ALTER TABLE Audit_Logs ADD COLUMN IF NOT EXISTS change_source VARCHAR(40) NOT NULL DEFAULT 'direct' AFTER changed_by;

DELIMITER $$

-- Immutability guards (unchanged from Milestone 2)
DROP TRIGGER IF EXISTS trg_auditlogs_no_update $$
CREATE TRIGGER trg_auditlogs_no_update BEFORE UPDATE ON Audit_Logs FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit_Logs is immutable: UPDATE not permitted';
END $$

DROP TRIGGER IF EXISTS trg_auditlogs_no_delete $$
CREATE TRIGGER trg_auditlogs_no_delete BEFORE DELETE ON Audit_Logs FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit_Logs is immutable: DELETE not permitted';
END $$

-- -----------------------------------------------------------------------------
-- service_logs  (feeds: service event text)
-- -----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_service_logs_ai $$
CREATE TRIGGER trg_service_logs_ai AFTER INSERT ON service_logs FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'service_logs', 'INSERT', NEW.dispatch_id,
      NULL,
      JSON_OBJECT(
            'dispatch_id', NEW.dispatch_id,
            'equipment_id', NEW.equipment_id,
            'customer_id', NEW.customer_id,
            'dispatch_date', NEW.dispatch_date,
            'technician', NEW.technician,
            'service_type', NEW.service_type,
            'hours_spent', NEW.hours_spent,
            'labor_cost', NEW.labor_cost,
            'resolution_summary', NEW.resolution_summary,
            'status', NEW.status),
      CONCAT('service_logs insert: ', NEW.dispatch_id));
END $$

DROP TRIGGER IF EXISTS trg_service_logs_bu $$
CREATE TRIGGER trg_service_logs_bu BEFORE UPDATE ON service_logs FOR EACH ROW
BEGIN
  -- a no-op update (every column unchanged) is not a change
  IF NOT (OLD.dispatch_id <=> NEW.dispatch_id
       AND OLD.equipment_id <=> NEW.equipment_id
       AND OLD.customer_id <=> NEW.customer_id
       AND OLD.dispatch_date <=> NEW.dispatch_date
       AND OLD.technician <=> NEW.technician
       AND OLD.service_type <=> NEW.service_type
       AND OLD.hours_spent <=> NEW.hours_spent
       AND OLD.labor_cost <=> NEW.labor_cost
       AND OLD.resolution_summary <=> NEW.resolution_summary
       AND OLD.status <=> NEW.status) THEN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'service_logs', 'UPDATE', OLD.dispatch_id,
      JSON_OBJECT(
            'dispatch_id', OLD.dispatch_id,
            'equipment_id', OLD.equipment_id,
            'customer_id', OLD.customer_id,
            'dispatch_date', OLD.dispatch_date,
            'technician', OLD.technician,
            'service_type', OLD.service_type,
            'hours_spent', OLD.hours_spent,
            'labor_cost', OLD.labor_cost,
            'resolution_summary', OLD.resolution_summary,
            'status', OLD.status),
      JSON_OBJECT(
            'dispatch_id', NEW.dispatch_id,
            'equipment_id', NEW.equipment_id,
            'customer_id', NEW.customer_id,
            'dispatch_date', NEW.dispatch_date,
            'technician', NEW.technician,
            'service_type', NEW.service_type,
            'hours_spent', NEW.hours_spent,
            'labor_cost', NEW.labor_cost,
            'resolution_summary', NEW.resolution_summary,
            'status', NEW.status),
      CONCAT('service_logs update: ', OLD.dispatch_id));
  END IF;
END $$

DROP TRIGGER IF EXISTS trg_service_logs_ad $$
CREATE TRIGGER trg_service_logs_ad AFTER DELETE ON service_logs FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'service_logs', 'DELETE', OLD.dispatch_id,
      JSON_OBJECT(
            'dispatch_id', OLD.dispatch_id,
            'equipment_id', OLD.equipment_id,
            'customer_id', OLD.customer_id,
            'dispatch_date', OLD.dispatch_date,
            'technician', OLD.technician,
            'service_type', OLD.service_type,
            'hours_spent', OLD.hours_spent,
            'labor_cost', OLD.labor_cost,
            'resolution_summary', OLD.resolution_summary,
            'status', OLD.status),
      NULL,
      CONCAT('service_logs delete: ', OLD.dispatch_id));
END $$

-- -----------------------------------------------------------------------------
-- warranty_claims  (feeds: claim text)
-- -----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_warranty_claims_ai $$
CREATE TRIGGER trg_warranty_claims_ai AFTER INSERT ON warranty_claims FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'warranty_claims', 'INSERT', NEW.claim_id,
      NULL,
      JSON_OBJECT(
            'claim_id', NEW.claim_id,
            'equipment_id', NEW.equipment_id,
            'dispatch_id', NEW.dispatch_id,
            'part_id', NEW.part_id,
            'claim_date', NEW.claim_date,
            'claim_amount', NEW.claim_amount,
            'approved_amount', NEW.approved_amount,
            'status', NEW.status,
            'denial_reason', NEW.denial_reason,
            'claim_notes', NEW.claim_notes),
      CONCAT('warranty_claims insert: ', NEW.claim_id));
END $$

DROP TRIGGER IF EXISTS trg_warranty_claims_bu $$
CREATE TRIGGER trg_warranty_claims_bu BEFORE UPDATE ON warranty_claims FOR EACH ROW
BEGIN
  -- a no-op update (every column unchanged) is not a change
  IF NOT (OLD.claim_id <=> NEW.claim_id
       AND OLD.equipment_id <=> NEW.equipment_id
       AND OLD.dispatch_id <=> NEW.dispatch_id
       AND OLD.part_id <=> NEW.part_id
       AND OLD.claim_date <=> NEW.claim_date
       AND OLD.claim_amount <=> NEW.claim_amount
       AND OLD.approved_amount <=> NEW.approved_amount
       AND OLD.status <=> NEW.status
       AND OLD.denial_reason <=> NEW.denial_reason
       AND OLD.claim_notes <=> NEW.claim_notes) THEN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'warranty_claims', 'UPDATE', OLD.claim_id,
      JSON_OBJECT(
            'claim_id', OLD.claim_id,
            'equipment_id', OLD.equipment_id,
            'dispatch_id', OLD.dispatch_id,
            'part_id', OLD.part_id,
            'claim_date', OLD.claim_date,
            'claim_amount', OLD.claim_amount,
            'approved_amount', OLD.approved_amount,
            'status', OLD.status,
            'denial_reason', OLD.denial_reason,
            'claim_notes', OLD.claim_notes),
      JSON_OBJECT(
            'claim_id', NEW.claim_id,
            'equipment_id', NEW.equipment_id,
            'dispatch_id', NEW.dispatch_id,
            'part_id', NEW.part_id,
            'claim_date', NEW.claim_date,
            'claim_amount', NEW.claim_amount,
            'approved_amount', NEW.approved_amount,
            'status', NEW.status,
            'denial_reason', NEW.denial_reason,
            'claim_notes', NEW.claim_notes),
      CONCAT('warranty_claims update: ', OLD.claim_id));
  END IF;
END $$

DROP TRIGGER IF EXISTS trg_warranty_claims_ad $$
CREATE TRIGGER trg_warranty_claims_ad AFTER DELETE ON warranty_claims FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'warranty_claims', 'DELETE', OLD.claim_id,
      JSON_OBJECT(
            'claim_id', OLD.claim_id,
            'equipment_id', OLD.equipment_id,
            'dispatch_id', OLD.dispatch_id,
            'part_id', OLD.part_id,
            'claim_date', OLD.claim_date,
            'claim_amount', OLD.claim_amount,
            'approved_amount', OLD.approved_amount,
            'status', OLD.status,
            'denial_reason', OLD.denial_reason,
            'claim_notes', OLD.claim_notes),
      NULL,
      CONCAT('warranty_claims delete: ', OLD.claim_id));
END $$

-- -----------------------------------------------------------------------------
-- equipment_units  (feeds: unit lines in every payload)
-- -----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_equipment_units_ai $$
CREATE TRIGGER trg_equipment_units_ai AFTER INSERT ON equipment_units FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'equipment_units', 'INSERT', NEW.equipment_id,
      NULL,
      JSON_OBJECT(
            'equipment_id', NEW.equipment_id,
            'customer_id', NEW.customer_id,
            'model', NEW.model,
            'serial_number', NEW.serial_number,
            'install_date', NEW.install_date,
            'warranty_expiration', NEW.warranty_expiration,
            'status', NEW.status,
            'location_notes', NEW.location_notes),
      CONCAT('equipment_units insert: ', NEW.equipment_id));
END $$

DROP TRIGGER IF EXISTS trg_equipment_units_bu $$
CREATE TRIGGER trg_equipment_units_bu BEFORE UPDATE ON equipment_units FOR EACH ROW
BEGIN
  -- a no-op update (every column unchanged) is not a change
  IF NOT (OLD.equipment_id <=> NEW.equipment_id
       AND OLD.customer_id <=> NEW.customer_id
       AND OLD.model <=> NEW.model
       AND OLD.serial_number <=> NEW.serial_number
       AND OLD.install_date <=> NEW.install_date
       AND OLD.warranty_expiration <=> NEW.warranty_expiration
       AND OLD.status <=> NEW.status
       AND OLD.location_notes <=> NEW.location_notes) THEN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'equipment_units', 'UPDATE', OLD.equipment_id,
      JSON_OBJECT(
            'equipment_id', OLD.equipment_id,
            'customer_id', OLD.customer_id,
            'model', OLD.model,
            'serial_number', OLD.serial_number,
            'install_date', OLD.install_date,
            'warranty_expiration', OLD.warranty_expiration,
            'status', OLD.status,
            'location_notes', OLD.location_notes),
      JSON_OBJECT(
            'equipment_id', NEW.equipment_id,
            'customer_id', NEW.customer_id,
            'model', NEW.model,
            'serial_number', NEW.serial_number,
            'install_date', NEW.install_date,
            'warranty_expiration', NEW.warranty_expiration,
            'status', NEW.status,
            'location_notes', NEW.location_notes),
      CONCAT('equipment_units update: ', OLD.equipment_id));
  END IF;
END $$

DROP TRIGGER IF EXISTS trg_equipment_units_ad $$
CREATE TRIGGER trg_equipment_units_ad AFTER DELETE ON equipment_units FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'equipment_units', 'DELETE', OLD.equipment_id,
      JSON_OBJECT(
            'equipment_id', OLD.equipment_id,
            'customer_id', OLD.customer_id,
            'model', OLD.model,
            'serial_number', OLD.serial_number,
            'install_date', OLD.install_date,
            'warranty_expiration', OLD.warranty_expiration,
            'status', OLD.status,
            'location_notes', OLD.location_notes),
      NULL,
      CONCAT('equipment_units delete: ', OLD.equipment_id));
END $$

-- -----------------------------------------------------------------------------
-- customers  (feeds: company name in payloads)
-- -----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_customers_ai $$
CREATE TRIGGER trg_customers_ai AFTER INSERT ON customers FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'customers', 'INSERT', NEW.customer_id,
      NULL,
      JSON_OBJECT(
            'customer_id', NEW.customer_id,
            'company_name', NEW.company_name,
            'contact_name', NEW.contact_name,
            'phone', NEW.phone,
            'email', NEW.email,
            'address', NEW.address,
            'zip', NEW.zip,
            'created_date', NEW.created_date,
            'status', NEW.status),
      CONCAT('customers insert: ', NEW.customer_id));
END $$

DROP TRIGGER IF EXISTS trg_customers_bu $$
CREATE TRIGGER trg_customers_bu BEFORE UPDATE ON customers FOR EACH ROW
BEGIN
  -- a no-op update (every column unchanged) is not a change
  IF NOT (OLD.customer_id <=> NEW.customer_id
       AND OLD.company_name <=> NEW.company_name
       AND OLD.contact_name <=> NEW.contact_name
       AND OLD.phone <=> NEW.phone
       AND OLD.email <=> NEW.email
       AND OLD.address <=> NEW.address
       AND OLD.zip <=> NEW.zip
       AND OLD.created_date <=> NEW.created_date
       AND OLD.status <=> NEW.status) THEN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'customers', 'UPDATE', OLD.customer_id,
      JSON_OBJECT(
            'customer_id', OLD.customer_id,
            'company_name', OLD.company_name,
            'contact_name', OLD.contact_name,
            'phone', OLD.phone,
            'email', OLD.email,
            'address', OLD.address,
            'zip', OLD.zip,
            'created_date', OLD.created_date,
            'status', OLD.status),
      JSON_OBJECT(
            'customer_id', NEW.customer_id,
            'company_name', NEW.company_name,
            'contact_name', NEW.contact_name,
            'phone', NEW.phone,
            'email', NEW.email,
            'address', NEW.address,
            'zip', NEW.zip,
            'created_date', NEW.created_date,
            'status', NEW.status),
      CONCAT('customers update: ', OLD.customer_id));
  END IF;
END $$

DROP TRIGGER IF EXISTS trg_customers_ad $$
CREATE TRIGGER trg_customers_ad AFTER DELETE ON customers FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'customers', 'DELETE', OLD.customer_id,
      JSON_OBJECT(
            'customer_id', OLD.customer_id,
            'company_name', OLD.company_name,
            'contact_name', OLD.contact_name,
            'phone', OLD.phone,
            'email', OLD.email,
            'address', OLD.address,
            'zip', OLD.zip,
            'created_date', OLD.created_date,
            'status', OLD.status),
      NULL,
      CONCAT('customers delete: ', OLD.customer_id));
END $$

-- -----------------------------------------------------------------------------
-- parts_inventory  (feeds: part and supplier in claims)
-- -----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_parts_inventory_ai $$
CREATE TRIGGER trg_parts_inventory_ai AFTER INSERT ON parts_inventory FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'parts_inventory', 'INSERT', NEW.part_id,
      NULL,
      JSON_OBJECT(
            'part_id', NEW.part_id,
            'part_name', NEW.part_name,
            'category', NEW.category,
            'manufacturer', NEW.manufacturer,
            'supplier', NEW.supplier,
            'unit_cost', NEW.unit_cost,
            'unit_price', NEW.unit_price,
            'stock_quantity', NEW.stock_quantity,
            'reorder_level', NEW.reorder_level),
      CONCAT('parts_inventory insert: ', NEW.part_id));
END $$

DROP TRIGGER IF EXISTS trg_parts_inventory_bu $$
CREATE TRIGGER trg_parts_inventory_bu BEFORE UPDATE ON parts_inventory FOR EACH ROW
BEGIN
  -- a no-op update (every column unchanged) is not a change
  IF NOT (OLD.part_id <=> NEW.part_id
       AND OLD.part_name <=> NEW.part_name
       AND OLD.category <=> NEW.category
       AND OLD.manufacturer <=> NEW.manufacturer
       AND OLD.supplier <=> NEW.supplier
       AND OLD.unit_cost <=> NEW.unit_cost
       AND OLD.unit_price <=> NEW.unit_price
       AND OLD.stock_quantity <=> NEW.stock_quantity
       AND OLD.reorder_level <=> NEW.reorder_level) THEN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'parts_inventory', 'UPDATE', OLD.part_id,
      JSON_OBJECT(
            'part_id', OLD.part_id,
            'part_name', OLD.part_name,
            'category', OLD.category,
            'manufacturer', OLD.manufacturer,
            'supplier', OLD.supplier,
            'unit_cost', OLD.unit_cost,
            'unit_price', OLD.unit_price,
            'stock_quantity', OLD.stock_quantity,
            'reorder_level', OLD.reorder_level),
      JSON_OBJECT(
            'part_id', NEW.part_id,
            'part_name', NEW.part_name,
            'category', NEW.category,
            'manufacturer', NEW.manufacturer,
            'supplier', NEW.supplier,
            'unit_cost', NEW.unit_cost,
            'unit_price', NEW.unit_price,
            'stock_quantity', NEW.stock_quantity,
            'reorder_level', NEW.reorder_level),
      CONCAT('parts_inventory update: ', OLD.part_id));
  END IF;
END $$

DROP TRIGGER IF EXISTS trg_parts_inventory_ad $$
CREATE TRIGGER trg_parts_inventory_ad AFTER DELETE ON parts_inventory FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'parts_inventory', 'DELETE', OLD.part_id,
      JSON_OBJECT(
            'part_id', OLD.part_id,
            'part_name', OLD.part_name,
            'category', OLD.category,
            'manufacturer', OLD.manufacturer,
            'supplier', OLD.supplier,
            'unit_cost', OLD.unit_cost,
            'unit_price', OLD.unit_price,
            'stock_quantity', OLD.stock_quantity,
            'reorder_level', OLD.reorder_level),
      NULL,
      CONCAT('parts_inventory delete: ', OLD.part_id));
END $$

-- -----------------------------------------------------------------------------
-- equipment_models  (feeds: kW and V in payloads)
-- -----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_equipment_models_ai $$
CREATE TRIGGER trg_equipment_models_ai AFTER INSERT ON equipment_models FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'equipment_models', 'INSERT', NEW.model,
      NULL,
      JSON_OBJECT(
            'model', NEW.model,
            'capacity_kw', NEW.capacity_kw,
            'voltage', NEW.voltage),
      CONCAT('equipment_models insert: ', NEW.model));
END $$

DROP TRIGGER IF EXISTS trg_equipment_models_bu $$
CREATE TRIGGER trg_equipment_models_bu BEFORE UPDATE ON equipment_models FOR EACH ROW
BEGIN
  -- a no-op update (every column unchanged) is not a change
  IF NOT (OLD.model <=> NEW.model
       AND OLD.capacity_kw <=> NEW.capacity_kw
       AND OLD.voltage <=> NEW.voltage) THEN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'equipment_models', 'UPDATE', OLD.model,
      JSON_OBJECT(
            'model', OLD.model,
            'capacity_kw', OLD.capacity_kw,
            'voltage', OLD.voltage),
      JSON_OBJECT(
            'model', NEW.model,
            'capacity_kw', NEW.capacity_kw,
            'voltage', NEW.voltage),
      CONCAT('equipment_models update: ', OLD.model));
  END IF;
END $$

DROP TRIGGER IF EXISTS trg_equipment_models_ad $$
CREATE TRIGGER trg_equipment_models_ad AFTER DELETE ON equipment_models FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'equipment_models', 'DELETE', OLD.model,
      JSON_OBJECT(
            'model', OLD.model,
            'capacity_kw', OLD.capacity_kw,
            'voltage', OLD.voltage),
      NULL,
      CONCAT('equipment_models delete: ', OLD.model));
END $$

-- -----------------------------------------------------------------------------
-- locations  (feeds: city and state in payloads)
-- -----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_locations_ai $$
CREATE TRIGGER trg_locations_ai AFTER INSERT ON locations FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'locations', 'INSERT', NEW.zip,
      NULL,
      JSON_OBJECT(
            'zip', NEW.zip,
            'city', NEW.city,
            'state', NEW.state,
            'country', NEW.country),
      CONCAT('locations insert: ', NEW.zip));
END $$

DROP TRIGGER IF EXISTS trg_locations_bu $$
CREATE TRIGGER trg_locations_bu BEFORE UPDATE ON locations FOR EACH ROW
BEGIN
  -- a no-op update (every column unchanged) is not a change
  IF NOT (OLD.zip <=> NEW.zip
       AND OLD.city <=> NEW.city
       AND OLD.state <=> NEW.state
       AND OLD.country <=> NEW.country) THEN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'locations', 'UPDATE', OLD.zip,
      JSON_OBJECT(
            'zip', OLD.zip,
            'city', OLD.city,
            'state', OLD.state,
            'country', OLD.country),
      JSON_OBJECT(
            'zip', NEW.zip,
            'city', NEW.city,
            'state', NEW.state,
            'country', NEW.country),
      CONCAT('locations update: ', OLD.zip));
  END IF;
END $$

DROP TRIGGER IF EXISTS trg_locations_ad $$
CREATE TRIGGER trg_locations_ad AFTER DELETE ON locations FOR EACH ROW
BEGIN
  INSERT INTO Audit_Logs (changed_by, change_source, table_name, operation_type, record_id,
                            old_values, new_values, change_desc)
    VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'locations', 'DELETE', OLD.zip,
      JSON_OBJECT(
            'zip', OLD.zip,
            'city', OLD.city,
            'state', OLD.state,
            'country', OLD.country),
      NULL,
      CONCAT('locations delete: ', OLD.zip));
END $$

DELIMITER ;
