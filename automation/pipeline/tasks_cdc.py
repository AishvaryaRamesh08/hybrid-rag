"""
tasks_cdc.py - change data capture: detect changes made DIRECTLY in MariaDB.

The landing-folder manifest catches new files. This task catches the other way data changes:
an application or a person running INSERT / UPDATE / DELETE on the Silver tables. The CDC
triggers (sql/11_cdc_triggers.sql) write every such change to Audit_Logs, tagged 'direct'.
The pipeline's own merge is tagged with its run ID, so it is ignored here.

How a change is consumed, exactly once:
    1. read the 'direct' Audit_Logs rows after the saved position (a high-water mark on audit_id)
    2. if there are any, raise the durable "payloads_stale" flag; the existing tasks then rebuild
       rag_payloads, re-embed only the payloads whose text changed, and clear the answer caches
    3. save the new position in the SAME transaction as the flag, so a crash can never record
       the position without the flag (a change lost) or the flag without the position (only a
       harmless repeat)

Why the position does not simply jump to MAX(audit_id): an ID is assigned when a row is
inserted, not when its transaction commits. A long transaction can hold ID 100 while ID 101 is
already committed. Jumping to 101 would skip 100 forever. So the position only advances
through IDs with no gap below them. A gap that is still open after GAP_TIMEOUT_S is treated as
a rolled-back transaction (rollbacks leave permanent gaps) and skipped.
"""
from config import get_logger, mariadb

POSITION = "cdc_audit_position"
STALE_FLAG = "payloads_stale"          # the same flag the ERP merge raises (tasks_erp.py)
GAP_TIMEOUT_S = 600                    # longer than any transaction this system runs
SCAN_LIMIT = 50000                     # rows read per run; the rest are read by the next run


def cdc_installed(cur):
    cur.execute("SELECT COUNT(*) n FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME='Audit_Logs' AND COLUMN_NAME='change_source'")
    return cur.fetchone()["n"] == 1


def advance(position, rows, now_ts):
    """The new position: the last ID reached without crossing an open gap.
    rows = [(audit_id, changed_at), ...] after `position`, sorted by audit_id."""
    for audit_id, changed_at in rows:
        if audit_id != position + 1 and (now_ts - changed_at).total_seconds() < GAP_TIMEOUT_S:
            break                       # an earlier ID may still commit: wait for it
        position = audit_id             # contiguous, or the gap is old enough to be a rollback
    return position


def detect(ctx):
    log = get_logger()
    conn = mariadb(autocommit=False)
    try:
        with conn.cursor() as cur:
            if not cdc_installed(cur):
                return {"status": "skipped", "message": "CDC triggers not installed (run sql/11_cdc_triggers.sql)"}
            cur.execute("SELECT state_value FROM etl_state WHERE state_key=%s", (POSITION,))
            row = cur.fetchone()
            if row is None:             # first run: start capturing from now, not from the M2 history
                cur.execute("SELECT COALESCE(MAX(audit_id), 0) n FROM Audit_Logs")
                start = int(cur.fetchone()["n"])
                cur.execute("REPLACE INTO etl_state (state_key, state_value) VALUES (%s, %s)", (POSITION, start))
                conn.commit()
                return {"status": "skipped", "message": f"CDC started at audit_id {start}"}
            position = int(row["state_value"])

            cur.execute("SELECT audit_id, changed_at FROM Audit_Logs WHERE audit_id > %s ORDER BY audit_id LIMIT %s",
                        (position, SCAN_LIMIT))
            rows = [(r["audit_id"], r["changed_at"]) for r in cur.fetchall()]
            cur.execute("SELECT NOW() now_ts")
            new_position = advance(position, rows, cur.fetchone()["now_ts"])
            if new_position == position:
                waiting = f"; {len(rows)} row(s) wait for an earlier transaction" if rows else ""
                conn.rollback()
                return {"status": "skipped", "message": f"no direct changes{waiting}"}

            cur.execute("SELECT table_name, operation_type, COUNT(*) n FROM Audit_Logs "
                        "WHERE audit_id > %s AND audit_id <= %s AND change_source='direct' "
                        "GROUP BY table_name, operation_type ORDER BY table_name, operation_type",
                        (position, new_position))
            changes = cur.fetchall()
            total = sum(int(c["n"]) for c in changes)
            if total:
                cur.execute("REPLACE INTO etl_state (state_key, state_value) VALUES (%s, '1')", (STALE_FLAG,))
            cur.execute("REPLACE INTO etl_state (state_key, state_value) VALUES (%s, %s)", (POSITION, new_position))
        conn.commit()                   # flag and position together, or neither
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    ctx["cdc_changed"] = total
    if not total:                       # only the pipeline's own tagged writes were passed
        return {"status": "skipped", "message": f"no direct changes (position {position} -> {new_position})"}
    detail = ", ".join(f"{c['n']} {c['operation_type']} {c['table_name']}" for c in changes)
    log.info(f"[cdc_detect] direct changes found: {detail}")
    return {"rows_in": len(rows), "rows_out": total,
            "message": f"{total} direct change(s): {detail}; rag_payloads marked for refresh "
                       f"(audit_id {position} -> {new_position})"}
