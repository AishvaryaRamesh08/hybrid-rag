"""
tasks_erp.py - incremental ERP loading: stage -> validate -> merge -> refresh RAG payloads.

A batch is any set of CSV files in landing/erp named after their table
(customers*.csv, equipment*.csv, dispatches*.csv, parts*.csv, warranty_claims*.csv).

    stage     load only the new files into the batch_* tables (a file whose header does
              not match the table layout is rejected whole, before any row is loaded)
    validate  rows that break a rule are copied to etl_quarantine with the reason and
              removed from the batch, so one bad row never blocks the good ones
    merge     the Milestone 1 cleansing SQL, as upserts, in ONE transaction; the same
              transaction raises the "payloads_stale" flag, so a crash after the commit
              cannot lose the fact that the RAG payloads need rebuilding
    refresh   rebuilds rag_payloads with the Milestone 2 stored procedure when the flag is set
              (raised by this merge, or by cdc_detect for changes made directly in MariaDB)
"""
import csv
from pathlib import Path

from config import mariadb

STAGING = {"customers": "batch_customers", "equipment": "batch_equipment", "dispatches": "batch_dispatches",
           "parts": "batch_parts", "warranty_claims": "batch_warranty_claims"}
MERGE_SQL = Path(__file__).resolve().parent.parent / "sql" / "09_incremental_merge.sql"
STALE_FLAG = "payloads_stale"
DATE_OK = ("'^[0-9]{4}-[0-9]{2}-[0-9]{2}(T.*)?$|^[0-9]{4}/[0-9]{2}/[0-9]{2}$|"
           "^[0-9]{2}/[0-9]{2}/[0-9]{4}$|^[0-9]{2}-[0-9]{2}-[0-9]{4}$'")
NUMBER_OK = "'^[0-9]+(\\\\.[0-9]+)?$'"


def K(col):
    """The cleaned key expression used by the cleansing SQL (HTML stripped, trimmed)."""
    return f"TRIM(REGEXP_REPLACE({col}, '<[^>]+>', ''))"


def blank(col):
    return f"({col} IS NULL OR {K(col)} = '' OR {K(col)} = 'NULL')"


def unknown(col, parent_table, parent_key, batch_table):
    """The key is neither in the Silver parent table nor arriving in this batch."""
    return (f"{K(col)} NOT IN (SELECT {parent_key} FROM {parent_table}) "
            f"AND {K(col)} NOT IN (SELECT {K(parent_key)} FROM {batch_table})")


# (batch table, key column, reason, WHERE clause). Order matters: parents are checked first,
# so a child of a quarantined parent is quarantined too.
RULES = [
    ("batch_customers", "customer_id", "missing customer_id", blank("customer_id")),
    ("batch_customers", "customer_id", "missing zip", blank("zip")),
    ("batch_equipment", "equipment_id", "missing equipment_id", blank("equipment_id")),
    ("batch_equipment", "equipment_id", "missing model", blank("model")),
    ("batch_equipment", "equipment_id", "unknown customer_id",
     f"NOT {blank('customer_id')} AND " + unknown("customer_id", "customers", "customer_id", "batch_customers")),
    ("batch_parts", "part_id", "missing part_id", blank("part_id")),
    ("batch_dispatches", "dispatch_id", "missing dispatch_id", blank("dispatch_id")),
    ("batch_dispatches", "dispatch_id", "unparseable dispatch_date", f"{K('dispatch_date')} NOT REGEXP {DATE_OK}"),
    ("batch_dispatches", "dispatch_id", "non-numeric hours_spent",
     f"NOT {blank('hours_spent')} AND {K('hours_spent')} NOT REGEXP {NUMBER_OK}"),
    ("batch_dispatches", "dispatch_id", "unknown equipment_id",
     unknown("equipment_id", "equipment_units", "equipment_id", "batch_equipment")),
    ("batch_dispatches", "dispatch_id", "unknown customer_id",
     unknown("customer_id", "customers", "customer_id", "batch_customers")),
    ("batch_warranty_claims", "claim_id", "missing claim_id", blank("claim_id")),
    ("batch_warranty_claims", "claim_id", "unparseable claim_date", f"{K('claim_date')} NOT REGEXP {DATE_OK}"),
    ("batch_warranty_claims", "claim_id", "non-numeric claim_amount",
     f"{K('claim_amount')} NOT REGEXP {NUMBER_OK}"),
    ("batch_warranty_claims", "claim_id", "unknown equipment_id",
     unknown("equipment_id", "equipment_units", "equipment_id", "batch_equipment")),
    ("batch_warranty_claims", "claim_id", "unknown dispatch_id",
     f"NOT {blank('dispatch_id')} AND " + unknown("dispatch_id", "service_logs", "dispatch_id", "batch_dispatches")),
    ("batch_warranty_claims", "claim_id", "unknown part_id",
     f"NOT {blank('part_id')} AND " + unknown("part_id", "parts_inventory", "part_id", "batch_parts")),
]


def table_for(path):
    name = Path(path).name.lower()
    for prefix in sorted(STAGING, key=len, reverse=True):     # "warranty_claims" before shorter names
        if name.startswith(prefix):
            return STAGING[prefix]
    return None


def erp_files(ctx):
    return [f for f in ctx["files"] if f["source"] == "erp"]


def reject(ctx, f, reason):
    """A whole file that cannot be loaded: recorded in the quarantine and never retried."""
    ctx["state"].quarantine(ctx["run_id"], "erp", f["path"], None, reason, {"file": f["path"].name})
    ctx.setdefault("rejected", {})[str(f["path"])] = reason


def stage(ctx):
    files = erp_files(ctx)
    if not files:
        return {"status": "skipped", "message": "no new ERP files"}
    conn = mariadb(local_infile=True)
    loaded, rejected = 0, []
    try:
        with conn.cursor() as cur:
            for table in STAGING.values():             # the batch tables hold only this batch
                cur.execute(f"TRUNCATE TABLE {table}")
            for f in files:
                table = table_for(f["path"])
                if not table:
                    reject(ctx, f, "unrecognized ERP file name")
                    rejected.append(f["path"].name)
                    continue
                cur.execute(f"SHOW COLUMNS FROM {table}")
                expected = [row["Field"].lower() for row in cur.fetchall()]
                with f["path"].open(newline="", encoding="utf-8-sig") as handle:
                    header = [h.strip().lower() for h in next(csv.reader(handle), [])]
                if header != expected:                 # LOAD DATA maps by position, so the layout must match
                    reject(ctx, f, f"header does not match {table}: {header[:12]}")
                    rejected.append(f["path"].name)
                    continue
                terminator = "\\r\\n" if b"\r\n" in f["path"].read_bytes()[:4096] else "\\n"
                cur.execute(f"LOAD DATA LOCAL INFILE %s INTO TABLE {table} CHARACTER SET utf8mb4 "
                            f"FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '{terminator}' IGNORE 1 LINES",
                            (str(f["path"]),))
                ctx.setdefault("rows_by_file", {})[str(f["path"])] = cur.rowcount
                loaded += cur.rowcount
    finally:
        conn.close()
    ctx["erp_staged"] = loaded
    msg = f"{loaded} rows staged from {len(files) - len(rejected)} file(s)"
    return {"rows_in": loaded, "rows_out": loaded, "message": msg + (f"; rejected {rejected}" if rejected else "")}


def validate(ctx):
    if not ctx.get("erp_staged"):
        return {"status": "skipped", "message": "nothing staged"}
    conn = mariadb()
    quarantined, reasons = 0, {}
    try:
        with conn.cursor() as cur:
            for table, key, reason, where in RULES:
                cur.execute(f"SELECT * FROM {table} WHERE {where}")
                bad = cur.fetchall()
                for row in bad:
                    ctx["state"].quarantine(ctx["run_id"], "erp", table, str(row.get(key)), reason, row)
                if bad:
                    cur.execute(f"DELETE FROM {table} WHERE {where}")
                    quarantined += len(bad)
                    reasons[reason] = reasons.get(reason, 0) + len(bad)
    finally:
        conn.close()
    ctx["erp_quarantined"] = quarantined
    kept = ctx["erp_staged"] - quarantined
    detail = "; ".join(f"{n} {r}" for r, n in reasons.items())
    return {"rows_in": ctx["erp_staged"], "rows_out": kept,
            "message": f"{kept} valid, {quarantined} quarantined" + (f" ({detail})" if detail else "")}


def is_upsert(sql):
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return "ON DUPLICATE KEY UPDATE" in code


def merge(ctx):
    if not ctx.get("erp_staged"):
        return {"status": "skipped", "message": "nothing staged"}
    statements = [s for s in MERGE_SQL.read_text().split("\n-- @@\n") if s.strip()]
    conn = mariadb(autocommit=False)
    affected = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SET @etl_run_id = %s", (ctx["run_id"],))     # CDC triggers tag these writes
            for sql in statements:
                cur.execute(sql)
                if is_upsert(sql):
                    affected += max(cur.rowcount, 0)
            if affected:
                cur.execute("REPLACE INTO etl_state (state_key, state_value) VALUES (%s, '1')", (STALE_FLAG,))
        conn.commit()                       # all or nothing: a failure leaves Silver and Bronze untouched
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()                        # the session variable ends with the connection
    ctx["erp_changed"] = affected
    return {"rows_in": ctx["erp_staged"] - ctx.get("erp_quarantined", 0), "rows_out": affected,
            "message": f"{affected} row changes merged (an insert counts 1, an update 2, an unchanged row 0)"}


def refresh_payloads(ctx):
    """Rebuilds the RAG context table. Driven by the durable flag, not by this run's files,
    so a run that crashed after the merge is completed by the next run."""
    if ctx["state"].get_flag(STALE_FLAG, "0") != "1":
        return {"status": "skipped", "message": "Silver tables unchanged; rag_payloads kept"}
    conn = mariadb()
    try:
        with conn.cursor() as cur:
            cur.execute("CALL sp_Prepare_RAG_Payloads(FALSE)")
            summary = cur.fetchall()
            while cur.nextset():
                pass
    finally:
        conn.close()
    ctx["state"].set_flag(STALE_FLAG, "0")
    total = sum(int(r["payloads_generated"]) for r in summary)
    return {"rows_out": total, "message": "; ".join(f"{r['payload_type']} {r['payloads_generated']}" for r in summary)}
