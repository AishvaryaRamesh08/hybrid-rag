#!/usr/bin/env python3
"""
run_pipeline.py - automated end-to-end data pipeline for the Gigavolt RAG system.

DAG (each arrow is a dependency):

    detect ─┬─> erp_stage -> erp_validate -> erp_merge ─┐
            │                              cdc_detect ──┴─> rag_payloads_refresh -> erp_vectors_sync ─┐
            ├─> telemetry_load ───────────────────────────────────────────────────────────────────────┤
            └─> documents_chunk -> documents_vectors_sync ────────────────────────────────────────────┴─> integrity_check -> context_refresh

    detect                 new or changed files in the landing folders (SHA-256 manifest)
    cdc_detect             rows changed directly in MariaDB (CDC triggers -> Audit_Logs)
    erp_*                  CSV batch -> batch tables -> quarantine bad rows -> upsert into 3NF tables (MariaDB)
    rag_payloads_refresh   rebuild the RAG context table with sp_Prepare_RAG_Payloads
    erp_vectors_sync       embed only the payloads that changed (ChromaDB gv_erp)
    telemetry_load         validate and upsert BMS readings (MongoDB)
    documents_*            chunk new PDFs/TXT, embed only changed chunks (ChromaDB gv_manuals)
    integrity_check        orphaned keys, duplicate keys, and every store in step with its source
    context_refresh        bump the data version, which invalidates every cached answer

The graph database stage is not part of this DAG: the supply-chain graph was excluded from
the project by the instructor in Milestone 5, and supplier questions are answered from
parts_inventory and the supply-chain documents.

Usage (on EC2, with config.env loaded):
    python run_pipeline.py              # one run
    python run_pipeline.py --watch 60   # poll the landing folders every 60 s
    python run_pipeline.py --status     # last runs, their tasks and the quarantine
"""
import argparse
import time
import uuid

from config import bump_data_version, chroma_client, get_logger, mariadb, mongo_collection, now
from orchestrator import FAILED, Pipeline, RunLock, Task
from state import State
import tasks_cdc
import tasks_erp
import tasks_telemetry
import tasks_vectors

# The task that decides whether a source's landing files count as processed.
FILE_DONE_TASK = {"erp": "erp_merge", "telemetry": "telemetry_load", "document": "documents_vectors_sync"}

ORPHAN_CHECKS = {
    "service_logs -> equipment_units": "SELECT COUNT(*) n FROM service_logs s LEFT JOIN equipment_units e "
        "ON e.equipment_id=s.equipment_id WHERE s.equipment_id IS NOT NULL AND e.equipment_id IS NULL",
    "service_logs -> customers": "SELECT COUNT(*) n FROM service_logs s LEFT JOIN customers c "
        "ON c.customer_id=s.customer_id WHERE s.customer_id IS NOT NULL AND c.customer_id IS NULL",
    "warranty_claims -> equipment_units": "SELECT COUNT(*) n FROM warranty_claims w LEFT JOIN equipment_units e "
        "ON e.equipment_id=w.equipment_id WHERE w.equipment_id IS NOT NULL AND e.equipment_id IS NULL",
    "warranty_claims -> service_logs": "SELECT COUNT(*) n FROM warranty_claims w LEFT JOIN service_logs s "
        "ON s.dispatch_id=w.dispatch_id WHERE w.dispatch_id IS NOT NULL AND s.dispatch_id IS NULL",
    "warranty_claims -> parts_inventory": "SELECT COUNT(*) n FROM warranty_claims w LEFT JOIN parts_inventory p "
        "ON p.part_id=w.part_id WHERE w.part_id IS NOT NULL AND p.part_id IS NULL",
    "equipment_units -> customers": "SELECT COUNT(*) n FROM equipment_units e LEFT JOIN customers c "
        "ON c.customer_id=e.customer_id WHERE e.customer_id IS NOT NULL AND c.customer_id IS NULL",
    "rag_payloads -> source records": "SELECT COUNT(*) n FROM rag_payloads p LEFT JOIN service_logs s "
        "ON p.source_table='service_logs' AND s.dispatch_id=p.source_id LEFT JOIN warranty_claims w "
        "ON p.source_table='warranty_claims' AND w.claim_id=p.source_id WHERE s.dispatch_id IS NULL AND w.claim_id IS NULL",
    "rag_payloads not yet in the vector store": "SELECT COUNT(*) n FROM rag_payloads p LEFT JOIN rag_vector_sync s "
        f"ON {tasks_vectors.ON_KEY} WHERE s.source_id IS NULL OR s.content_hash <> {tasks_vectors.HASH}",
}


def detect(ctx):
    files = ctx["state"].detect_new_files()
    ctx["files"] = files
    if files:
        ctx["state"].register_files(files, ctx["run_id"])
    by_type = {}
    for f in files:
        by_type[f["source"]] = by_type.get(f["source"], 0) + 1
    return {"rows_out": len(files), "message": f"{len(files)} new or changed file(s) {by_type}" if files else "no new data"}


def integrity_check(ctx):
    """Zero-integrity-error gate. Runs even when a branch failed, so partial work is still verified."""
    problems = []
    conn = mariadb()
    try:
        with conn.cursor() as cur:
            for name, sql in ORPHAN_CHECKS.items():
                cur.execute(sql)
                n = cur.fetchone()["n"]
                if n:
                    problems.append(f"{n} rows: {name}")
            cur.execute("SELECT (SELECT COUNT(*) FROM service_logs) service_logs, "
                        "(SELECT COUNT(*) FROM warranty_claims) warranty_claims, "
                        "(SELECT COUNT(*) FROM rag_payloads) rag_payloads, "
                        "(SELECT COALESCE(SUM(part_count), 0) FROM rag_vector_sync) expected_erp_vectors")
            counts = cur.fetchone()
    finally:
        conn.close()
    telemetry = mongo_collection()
    counts["telemetry"] = telemetry.count_documents({})
    incomplete = telemetry.count_documents({"$or": [{"equipment_id": None}, {"timestamp": None}, {"model_key": None}]})
    if incomplete:
        problems.append(f"{incomplete} telemetry documents missing equipment_id, timestamp or model")
    collections = {c.name: c.count() for c in chroma_client().list_collections()}
    if collections.get("gv_erp") != int(counts["expected_erp_vectors"]):
        problems.append(f"gv_erp holds {collections.get('gv_erp')} vectors, expected {counts['expected_erp_vectors']}")
    ctx["store_counts"] = {**{k: int(v) for k, v in counts.items()}, **collections}
    if problems:
        raise RuntimeError("; ".join(problems))
    return {"message": f"0 integrity errors; {ctx['store_counts']}"}


def context_refresh(ctx):
    """Bumps the data version. Every cached answer is keyed by it, so new data clears the caches,
    and a running question-answering process reopens its vector collections."""
    changed = sum(ctx.get(k, 0) or 0 for k in ("erp_changed", "cdc_changed", "telemetry_changed", "vectors_changed"))
    if not changed:
        return {"status": "skipped", "message": "no data changed; caches kept"}
    bump_data_version(ctx["run_id"])
    return {"rows_out": changed, "message": f"data version set to {ctx['run_id']}; answer caches invalidated"}


PIPELINE = Pipeline([
    Task("detect", detect),
    Task("cdc_detect", tasks_cdc.detect),
    Task("erp_stage", tasks_erp.stage, ["detect"]),
    Task("erp_validate", tasks_erp.validate, ["erp_stage"]),
    Task("erp_merge", tasks_erp.merge, ["erp_validate"]),
    Task("rag_payloads_refresh", tasks_erp.refresh_payloads, ["erp_merge", "cdc_detect"]),
    Task("erp_vectors_sync", tasks_vectors.sync_erp_vectors, ["rag_payloads_refresh"]),
    Task("telemetry_load", tasks_telemetry.load, ["detect"]),
    Task("documents_chunk", tasks_vectors.chunk_documents, ["detect"]),
    Task("documents_vectors_sync", tasks_vectors.sync_documents, ["documents_chunk"]),
    Task("integrity_check", integrity_check, ["erp_vectors_sync", "telemetry_load", "documents_vectors_sync"],
         retries=1, trigger="all_done"),
    Task("context_refresh", context_refresh, ["integrity_check"], retries=0, trigger="all_done"),
])


def close_files(ctx, results, state, run_id):
    """A file is processed once its own branch loaded it; derived stores are tracked by flags and hashes."""
    for f in ctx["files"]:
        if str(f["path"]) in ctx.get("rejected", {}):
            status = "rejected"
        elif results[FILE_DONE_TASK[f["source"]]]["status"] in FAILED or results["detect"]["status"] in FAILED:
            status = "failed"
        else:
            status = "processed"
        state.mark_file(f, status, run_id, ctx.get("rows_by_file", {}).get(str(f["path"])))


def run_once(trigger="manual"):
    log = get_logger()
    run_id = now().strftime("run-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    with RunLock():
        state = State()
        ctx = {"run_id": run_id, "state": state, "files": []}
        state.start_run(run_id, trigger)
        log.info(f"=== {run_id} started ({trigger}) ===")
        start = time.perf_counter()
        results = PIPELINE.run(ctx, state, run_id)
        failed = [n for n, r in results.items() if r["status"] in FAILED]
        worked = any(r["status"] == "success" and n not in ("detect", "integrity_check") for n, r in results.items())
        status = "failed" if failed else ("success" if worked else "no_changes")
        close_files(ctx, results, state, run_id)
        summary = {"seconds": round(time.perf_counter() - start, 1), "files": len(ctx["files"]),
                   "quarantined_rows": ctx.get("erp_quarantined", 0) + ctx.get("telemetry_rejected", 0),
                   "direct_db_changes": ctx.get("cdc_changed", 0),
                   "tasks": {n: r["status"] for n, r in results.items()}, "store_counts": ctx.get("store_counts")}
        state.finish_run(run_id, status, summary)
        log.info(f"=== {run_id} {status} in {summary['seconds']} s"
                 + (f"; failed: {', '.join(failed)}" if failed else "") + " ===")
        return status


def show_status(runs=3):
    """Prints the last runs from MariaDB: the audit trail of what the pipeline did."""
    conn = mariadb()
    with conn.cursor() as cur:
        cur.execute("SELECT run_id, status, trigger_type, started_at, TIMESTAMPDIFF(MICROSECOND, started_at, finished_at)/1e6 s "
                    "FROM etl_runs ORDER BY started_at DESC LIMIT %s", (runs,))
        for run in cur.fetchall():
            print(f"\n{run['run_id']}  {run['status']}  ({run['trigger_type']}, {run['s'] or 0:.1f} s)")
            cur.execute("SELECT task, status, duration_ms, attempts, rows_in, rows_out, message FROM etl_task_runs "
                        "WHERE run_id=%s", (run["run_id"],))
            for t in sorted(cur.fetchall(), key=lambda t: PIPELINE.order.index(t["task"])):
                print(f"  {t['task']:<24}{t['status']:<9}{t['duration_ms'] or 0:>7} ms  tries={t['attempts']}  {t['message'] or ''}")
            cur.execute("SELECT source_type, reason, COUNT(*) n FROM etl_quarantine WHERE run_id=%s GROUP BY 1,2", (run["run_id"],))
            for q in cur.fetchall():
                print(f"  quarantined: {q['n']} {q['source_type']} - {q['reason']}")
    conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watch", type=int, metavar="SECONDS", help="poll the landing folders on this interval")
    ap.add_argument("--status", action="store_true", help="show the last runs and exit")
    ap.add_argument("--trigger", default="manual", help="label stored with the run (manual, timer)")
    args = ap.parse_args()
    if args.status:
        return show_status()
    if not args.watch:
        raise SystemExit(0 if run_once(args.trigger) in ("success", "no_changes") else 1)
    get_logger().info(f"Watching landing folders every {args.watch} s (Ctrl+C to stop)")
    while True:
        try:
            run_once("watch")
        except SystemExit as exc:
            get_logger().warning(str(exc))
        except Exception as exc:  # noqa: BLE001 - the watcher must survive a failed run
            get_logger().error(f"run crashed: {exc}")
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
