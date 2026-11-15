#!/usr/bin/env python3
"""
sql_tuning.py - before/after evidence for the SQL optimizations.

For each retriever query it prints the query plan (EXPLAIN) and the median time of 200 runs,
first WITHOUT the Milestone 6 indexes and then WITH them. The claim lookup is compared as two
query texts: the Milestone 5 LIKE scan and the Milestone 6 primary-key join.
It leaves the database in the tuned state (sql/10_index_tuning.sql).

Output: printed, and written to results/m6_sql_tuning.md

Usage (on EC2, config.env loaded):  python sql_tuning.py [--unit EQ-7171] [--claim CLM-9208]
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
RUNS = 200

UNIT = ("SELECT eu.equipment_id, eu.model FROM equipment_units eu WHERE eu.equipment_id=%s OR eu.serial_number=%s")
HISTORY = ("SELECT source_id, event_date FROM rag_payloads WHERE equipment_id=%s ORDER BY event_date DESC LIMIT 12")
WINDOW = ("SELECT source_id, event_date FROM rag_payloads WHERE equipment_id=%s AND event_date >= '2021-01-01' "
          "AND event_date < '2022-01-01' ORDER BY event_date DESC LIMIT 12")
CLAIM_M5 = "SELECT source_id FROM rag_payloads WHERE source_id=%s OR payload_text LIKE %s"
CLAIM_M6 = ("SELECT source_id FROM rag_payloads WHERE source_table IN ('service_logs','warranty_claims') AND source_id=%s UNION SELECT p.source_id FROM warranty_claims wc "
            "JOIN rag_payloads p ON p.source_table='service_logs' AND p.source_id=wc.dispatch_id "
            "AND p.equipment_id=wc.equipment_id WHERE wc.claim_id=%s")

DROP = ["DROP INDEX IF EXISTS idx_serial ON equipment_units", "DROP INDEX IF EXISTS idx_equip_date ON rag_payloads",
        "CREATE INDEX IF NOT EXISTS idx_equip ON rag_payloads (equipment_id)"]
CREATE = ["CREATE INDEX IF NOT EXISTS idx_serial ON equipment_units (serial_number)",
          "CREATE INDEX IF NOT EXISTS idx_equip_date ON rag_payloads (equipment_id, event_date)",
          "DROP INDEX IF EXISTS idx_equip ON rag_payloads",
          "ANALYZE TABLE equipment_units, rag_payloads"]


def measure(cur, sql, params):
    cur.execute("EXPLAIN " + sql, params)
    plan = "; ".join(f"{r['table']}: type={r['type']}, key={r['key']}, rows={r['rows']}"
                     + (f", {r['Extra']}" if r.get("Extra") else "") for r in cur.fetchall())
    times = []
    for _ in range(RUNS):
        start = time.perf_counter()
        cur.execute(sql, params)
        cur.fetchall()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times), plan


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", default="EQ-7171")
    ap.add_argument("--claim", default="CLM-9208")
    args = ap.parse_args()
    conn = mariadb()
    cur = conn.cursor()
    cur.execute("SELECT serial_number FROM equipment_units WHERE equipment_id=%s", (args.unit,))
    serial = cur.fetchone()["serial_number"]

    cases = [("Unit lookup by ID or serial", UNIT, UNIT, (serial, serial)),
             ("Unit history, newest first", HISTORY, HISTORY, (args.unit,)),
             ("Unit history in a date window", WINDOW, WINDOW, (args.unit,))]
    for statement in DROP:
        cur.execute(statement)
    before = [measure(cur, sql, params) for _, sql, _, params in cases]
    before.append(measure(cur, CLAIM_M5, (args.claim, f"%Warranty Claim {args.claim} |%")))
    for statement in CREATE:
        cur.execute(statement)
        cur.fetchall()
    after = [measure(cur, sql, params) for _, _, sql, params in cases]
    after.append(measure(cur, CLAIM_M6, (args.claim, args.claim)))
    conn.close()

    names = [c[0] for c in cases] + ["Claim lookup (LIKE scan -> primary-key join)"]
    lines = ["# SQL tuning: before and after", "",
             f"Median of {RUNS} executions per query, in milliseconds. 'Before' is the Milestone 5 schema and query "
             "text; 'after' is with sql/10_index_tuning.sql and the Milestone 6 query text.", "",
             "| Query | Before (ms) | After (ms) | Speed-up |", "|---|---:|---:|---:|"]
    for name, (b, _), (a, _) in zip(names, before, after):
        lines.append(f"| {name} | {b:.3f} | {a:.3f} | {b / a:.1f}x |")
    lines += ["", "## Query plans", ""]
    for name, (_, pb), (_, pa) in zip(names, before, after):
        lines += [f"**{name}**", "", f"- before: `{pb}`", f"- after: `{pa}`", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "m6_sql_tuning.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
