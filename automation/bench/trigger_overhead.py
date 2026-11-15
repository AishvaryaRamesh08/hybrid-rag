#!/usr/bin/env python3
"""
trigger_overhead.py - how much do the CDC triggers slow down writes?

Runs the same writes against a copy of service_logs twice, without and with a CDC trigger
that has the same shape as sql/11_cdc_triggers.sql (full-row JSON snapshot into an audit
table, no-op updates skipped). The live tables are never touched: the copies are created
at the start and dropped at the end.

Workloads (median of --repeat runs each):
    single-row INSERT   N separate autocommitted inserts      (an application saving records)
    single-row UPDATE   N separate autocommitted updates      (an application editing records)
    bulk INSERT         one INSERT ... SELECT of 5,000 rows    (a large batch merge)
    bulk no-op upsert   the same 5,000 rows again, unchanged   (what the merge does to old rows)

Output: printed, and written to results/m6_trigger_overhead.md
Usage (on EC2, config.env loaded):  python trigger_overhead.py [--rows 1000] [--repeat 3]
"""
import argparse
import os
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pipeline"))
from config import mariadb  # noqa: E402

OUT = Path(os.environ.get("BENCH_RESULTS", HERE.parent / "results"))
COLS = ["dispatch_id", "equipment_id", "customer_id", "dispatch_date", "technician", "service_type",
        "hours_spent", "labor_cost", "resolution_summary", "status"]


def snapshot(prefix):
    return "JSON_OBJECT(" + ", ".join(f"'{c}', {prefix}.{c}" for c in COLS) + ")"


TRIGGERS = [
    f"""CREATE TRIGGER bench_trg_ai AFTER INSERT ON bench_service_logs FOR EACH ROW
        INSERT INTO bench_audit (changed_by, change_source, table_name, operation_type, record_id, old_values, new_values, change_desc)
        VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'service_logs', 'INSERT', NEW.dispatch_id, NULL, {snapshot('NEW')},
                CONCAT('service_logs insert: ', NEW.dispatch_id))""",
    f"""CREATE TRIGGER bench_trg_bu BEFORE UPDATE ON bench_service_logs FOR EACH ROW
        IF NOT ({' AND '.join(f'OLD.{c} <=> NEW.{c}' for c in COLS)}) THEN
          INSERT INTO bench_audit (changed_by, change_source, table_name, operation_type, record_id, old_values, new_values, change_desc)
          VALUES (USER(), COALESCE(@etl_run_id, 'direct'), 'service_logs', 'UPDATE', OLD.dispatch_id, {snapshot('OLD')}, {snapshot('NEW')},
                  CONCAT('service_logs update: ', OLD.dispatch_id));
        END IF""",
]


def timed(func):
    start = time.perf_counter()
    func()
    return (time.perf_counter() - start) * 1000


def workloads(cur, rows):
    """Returns {workload: milliseconds} for one pass on empty copies."""
    cur.execute("TRUNCATE bench_service_logs")
    cur.execute("TRUNCATE bench_audit")
    ids = [f"BENCH-{i:06d}" for i in range(rows)]
    out = {}

    def single_inserts():
        for i in ids:
            cur.execute("INSERT INTO bench_service_logs (dispatch_id, equipment_id, dispatch_date, technician, service_type, "
                        "hours_spent, labor_cost, resolution_summary, status) VALUES (%s, 'EQ-0001', CURDATE(), 'Bench Tech', "
                        "'Diagnostic', 1.5, 180.00, 'Benchmark row', 'Pending')", (i,))

    def single_updates():
        for i in ids:
            cur.execute("UPDATE bench_service_logs SET status='Completed' WHERE dispatch_id=%s", (i,))

    out["single-row INSERT"] = timed(single_inserts)
    out["single-row UPDATE"] = timed(single_updates)
    cur.execute("TRUNCATE bench_service_logs")
    out["bulk INSERT (5,000 rows)"] = timed(lambda: cur.execute(
        "INSERT INTO bench_service_logs SELECT * FROM service_logs ORDER BY dispatch_id LIMIT 5000"))
    out["bulk no-op upsert (5,000 rows)"] = timed(lambda: cur.execute(
        "INSERT INTO bench_service_logs SELECT * FROM service_logs ORDER BY dispatch_id LIMIT 5000 "
        "ON DUPLICATE KEY UPDATE status=VALUES(status), technician=VALUES(technician)"))
    cur.execute("SELECT COUNT(*) n FROM bench_audit")
    out["audit rows written"] = cur.fetchone()["n"]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=1000, help="rows for the single-row workloads")
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()
    conn = mariadb(autocommit=True)
    cur = conn.cursor()
    results = {}
    try:
        cur.execute("DROP TABLE IF EXISTS bench_service_logs, bench_audit")
        cur.execute("CREATE TABLE bench_service_logs LIKE service_logs")
        cur.execute("CREATE TABLE bench_audit LIKE Audit_Logs")       # copies columns and indexes, not the guards
        for mode in ("without trigger", "with CDC trigger"):
            if mode == "with CDC trigger":
                for sql in TRIGGERS:
                    cur.execute(sql)
            passes = [workloads(cur, args.rows) for _ in range(args.repeat)]
            results[mode] = {k: statistics.median(p[k] for p in passes) for k in passes[0]}
            print(f"{mode}: {results[mode]}")
    finally:
        cur.execute("DROP TABLE IF EXISTS bench_service_logs, bench_audit")      # drops the triggers too
        conn.close()

    base, trig = results["without trigger"], results["with CDC trigger"]
    lines = ["# CDC trigger overhead", "",
             f"Median of {args.repeat} runs, in milliseconds, on copies of service_logs and Audit_Logs. "
             f"Single-row workloads use {args.rows} separate autocommitted statements.", "",
             "| Workload | Without trigger (ms) | With CDC trigger (ms) | Per row without (ms) | Per row with (ms) | Overhead |",
             "|---|---:|---:|---:|---:|---:|"]
    for name in [k for k in base if k != "audit rows written"]:
        n = args.rows if name.startswith("single") else 5000
        lines.append(f"| {name} | {base[name]:.0f} | {trig[name]:.0f} | {base[name] / n:.3f} | {trig[name] / n:.3f} | "
                     f"{100 * (trig[name] - base[name]) / base[name]:+.0f}% |")
    lines += ["", f"Audit rows written per pass with the trigger: {trig['audit rows written']} "
              f"({args.rows} inserts + {args.rows} updates + 5,000 bulk inserts; the no-op upsert wrote none)."]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "m6_trigger_overhead.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
