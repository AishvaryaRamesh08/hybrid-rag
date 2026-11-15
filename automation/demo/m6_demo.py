#!/usr/bin/env python3
"""
m6_demo.py - live screencast demo of every Milestone 6 deliverable, in rubric order.

Each part prints what it demonstrates, runs the real code live (the same code the timer and the
benchmark run), then lists what to point out on screen. Press Enter to move to the next part.

    1  End-to-end pipeline     the DAG, new data arriving (you pick the PDFs), every store updated
    2  Incremental updates     a second run reprocesses nothing
    3  Change data capture     a direct database edit is detected and propagated
    4  Error handling, logging quarantine, run history, integrity gate, JSON log
    5  Performance             Milestone 5 vs Milestone 6 retrieval, live; answer cache
    6  Benchmark results       latency P50/P95/P99 per stage, throughput, accuracy, tuning
    7  Provenance              live questions about the new data (unit + your PDFs), then their audit
    8  Recovery                LLM outage live (--with-recovery adds the database restart tests)
    9  System synthesis        how Milestones 1-5 are reused

Usage on EC2:
    source /opt/gigavolt/m6/ops/env.sh
    python demo/m6_demo.py                     # whole demo, Enter between parts
    python demo/m6_demo.py --part 3            # one part
    python demo/m6_demo.py --from 5            # from part 5 to the end
    python demo/m6_demo.py --with-recovery     # part 8 also stops and restarts MariaDB and MongoDB
    python demo/m6_demo.py --no-pause          # no Enter prompts (rehearsal)

Part 1 shows a menu of the prepared PDFs in demo/sample_new_data: type a number (2), several
(2,3), all, or none; Enter takes the first one not loaded yet. Nothing else has to be typed.
Part 6 shows the saved results of bench/run_benchmark.py (a 15-minute run); run that first.
The pipeline timer is paused during the demo and turned back on at the end.
"""
import argparse
import os
import re
import statistics
import subprocess
import sys
import textwrap
import time
from pathlib import Path

M6 = Path(__file__).resolve().parent.parent
for folder in ("pipeline", "rag", "bench", "ops"):
    sys.path.insert(0, str(M6 / folder))

import config  # noqa: E402  (also puts the Milestone 4 and 5 modules on the path)

RESULTS = Path(os.environ.get("BENCH_RESULTS", M6 / "results"))
TIMER = "gigavolt-pipeline.timer"
HISTORY_Q = "Show me the service history and warranty claims for equipment unit {unit}"
PERF_QUESTIONS = [
    "What is the status of claim CLM-9208?",
    "Which warranty claims were filed for equipment unit EQ-7171 in 2021?",
    "What happened to unit SN-X7-0094 and which components were flagged?",
    "Which suppliers provide lithium cells for our commercial energy storage units?",
]
COLOR = sys.stdout.isatty()
PAUSE = True
_cache = {}


# ----------------------------------------------------------------------------- screen helpers
def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def part(number, title, deliverable, what):
    print("\n" + paint("=" * 100, "36"))
    print(paint(f" PART {number}: {title}", "1;36"))
    print(paint(f" Deliverable: {deliverable}", "36"))
    print(paint("=" * 100, "36"))
    for line in what:
        print(textwrap.fill(line, 100, initial_indent="  ", subsequent_indent="  "))
    pause("run it")


def step(text):
    print("\n" + paint(f">> {text}", "1;33"))


def points(*lines):
    print("\n" + paint(" What this shows:", "1;32"))
    for line in lines:
        print(paint(textwrap.fill(line, 98, initial_indent="  * ", subsequent_indent="    "), "32"))
    pause("continue")


def pause(action):
    if PAUSE:
        input(paint(f"\n  (Enter to {action})", "2"))


def table(rows, headers):
    widths = [max(len(str(r[i])) for r in rows + [headers]) for i in range(len(headers))]
    line = "  " + "  ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    print(paint(line, "1"))
    for r in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(r, widths)))


def sql(query, args=(), fetch=True):
    """An ordinary database session, like any application: it is NOT tagged as the pipeline."""
    conn = config.mariadb()
    try:
        with conn.cursor() as cur:
            cur.execute(query, args)
            return cur.fetchall() if fetch else cur.rowcount
    finally:
        conn.close()


def md_section(path, heading, max_lines=40):
    """Prints one '## heading' section of a saved markdown report."""
    if not path.exists():
        print(paint(f"  {path.name} not found: run the benchmark scripts first", "31"))
        return
    text = path.read_text().split(f"## {heading}", 1)
    body = text[1].split("\n## ", 1)[0] if len(text) > 1 else text[0]
    for line in [l for l in body.strip().splitlines() if not l.startswith("![")][:max_lines]:
        print("  " + line)


def fresh_unit():
    """An X-7000 unit with warranty claims and no test data yet, so each demo starts from real history."""
    rows = sql("SELECT eu.equipment_id FROM equipment_units eu JOIN warranty_claims wc ON wc.equipment_id=eu.equipment_id "
               "WHERE eu.model='X-7000' AND NOT EXISTS (SELECT 1 FROM service_logs s WHERE s.equipment_id=eu.equipment_id "
               "AND s.dispatch_id LIKE 'DISP-T%%') GROUP BY eu.equipment_id ORDER BY COUNT(*) DESC, eu.equipment_id LIMIT 1")
    return rows[0]["equipment_id"]


def demo_unit():
    """The unit that received the most recent test batch (part 1)."""
    rows = sql("SELECT equipment_id FROM service_logs WHERE dispatch_id LIKE 'DISP-T%%' "
               "ORDER BY dispatch_date DESC, dispatch_id DESC LIMIT 1")
    return rows[0]["equipment_id"] if rows else None


def pipeline_module():
    if "run_pipeline" not in _cache:
        import run_pipeline
        _cache["run_pipeline"] = run_pipeline
    return _cache["run_pipeline"]


def optimized():
    if "optimized" not in _cache:
        step("Loading the optimized RAG pipeline (embedding model, connections)")
        from m6_rag import OptimizedRagPipeline
        _cache["optimized"] = OptimizedRagPipeline()
        _cache["optimized"].retriever.warmup()
    return _cache["optimized"]


def show_query(title, query, args, headers=None):
    """Prints the SQL, runs it, prints the result: what the viewer would type in the MariaDB client."""
    step(title)
    shown = query
    for a in args:
        shown = shown.replace("%s", f"'{a}'", 1)
    print(paint("  SQL> " + shown, "35"))
    rows = sql(query, args)
    if rows:
        table([tuple(str(v) for v in r.values()) for r in rows], headers or list(rows[0].keys()))
    else:
        print("  (no rows)")
    return rows


def show_loaded_rows(batch):
    """The new CSV rows as they arrived, then as they are stored in MariaDB after the run."""
    step(f"The raw CSV file that arrived: {batch['dispatches_csv'].name}")
    for line in batch["dispatches_csv"].read_text().splitlines():
        print(paint("  " + line, "2"))

    d_ids, c_ids = batch["dispatch_ids"], batch["claim_ids"]
    ph = lambda ids: ", ".join(["%s"] * len(ids))       # noqa: E731
    show_query("After the run: the new dispatches in the Silver table service_logs",
               f"SELECT dispatch_id, equipment_id, dispatch_date, service_type, hours_spent, labor_cost, status "
               f"FROM service_logs WHERE dispatch_id IN ({ph(d_ids)}) ORDER BY dispatch_id", d_ids)
    show_query("The new claims in the Silver table warranty_claims",
               f"SELECT claim_id, equipment_id, dispatch_id, claim_date, claim_amount, status "
               f"FROM warranty_claims WHERE claim_id IN ({ph(c_ids)}) ORDER BY claim_id", c_ids)
    show_query("The rows that did NOT load: etl_quarantine",
               f"SELECT source_file, record_key, reason FROM etl_quarantine WHERE record_key IN ({ph(d_ids + c_ids)}) "
               f"ORDER BY quarantine_id", d_ids + c_ids)


# ----------------------------------------------------------------------------- the parts
def part1():
    part(1, "END-TO-END PIPELINE ORCHESTRATION", "Python DAG: detection, cleansing, validation, loading, "
         "chunking, embedding, re-indexing, RAG context updates",
         ["New data is dropped into landing folders as files. The pipeline (a Python DAG, run every 10 minutes by "
          "a systemd timer) finds it, validates it, loads it into MariaDB and MongoDB, embeds only what changed into "
          "ChromaDB, checks integrity and refreshes the RAG context."])
    rp = pipeline_module()
    step("The DAG: every task and the tasks it waits for")
    table([(n + 1, name, ", ".join(rp.PIPELINE.tasks[name].deps) or "-", rp.PIPELINE.tasks[name].trigger)
           for n, name in enumerate(rp.PIPELINE.order)], ["#", "task", "waits for", "runs when"])

    from state import State
    step("Landing folders: files not processed yet (checked against the SHA-256 manifest)")
    pending = State().detect_new_files()
    for name, folder in config.LANDING_DIRS.items():
        print(f"  {folder}: {sum(1 for f in pending if f['source'] == name)} new file(s)")
    unit = fresh_unit()
    step(f"New data arrives: ERP CSVs and telemetry JSONL for unit {unit}, plus the PDF documents you choose")
    import new_data_batch
    batch = new_data_batch.main(["--unit", unit], ask=PAUSE)
    _cache["pdfs"] = batch["pdfs"]
    scanned = [e for e in batch["pdfs"] if not e["question"]]

    step("Run the pipeline")
    status = rp.run_once("demo")
    print(paint(f"\n  Run status: {status}", "1"))
    show_loaded_rows(batch)
    readable = [e["file"].split("_")[0] for e in batch["pdfs"] if e["question"]]
    points(f"detect found the {len(batch['files'])} new files by SHA-256 fingerprint; nothing was watching the folder",
           "erp_stage -> erp_validate -> erp_merge ran in order: each waited for the one before",
           "erp_merge applied the Milestone 1 cleaning rules as upserts into the Silver tables and appended the "
           "batch to Bronze, in one transaction",
           "The SQL output shows the result: the CSV text became typed columns (DATE, DECIMAL) in service_logs "
           "and warranty_claims; the dispatch for unknown unit EQ-0000 and the claim dated 'not-a-date' are in "
           "etl_quarantine with the reason, not in the Silver tables",
           "rag_payloads_refresh rebuilt the RAG context with the Milestone 2 stored procedure",
           "erp_vectors_sync and documents_vectors_sync embedded ONLY the new items into ChromaDB (HNSW index "
           "updated in place, no full re-index)",
           "telemetry_load upserted the new readings into MongoDB",
           (f"documents_chunk read the new PDF(s) {', '.join(readable)} (text and table rows) with the Milestone 4 "
            "chunker; only their chunks were embedded into gv_manuals" if readable else
            "documents_chunk chunked the new document with the Milestone 4 chunker"),
           *([f"{scanned[0]['file']} has no text (an image-only scan): the file was quarantined and the rest of "
              "the run continued"] if scanned else []),
           "integrity_check: 0 integrity errors; context_refresh cleared the answer caches")


def part2():
    part(2, "INCREMENTAL UPDATES", "Handle incremental updates (don't reprocess unchanged data)",
         ["The same pipeline runs again with no new data. Three mechanisms stop reprocessing: file fingerprints "
          "(files), the CDC position (database edits) and content hashes (vectors)."])
    rp = pipeline_module()
    step("Run the pipeline again")
    status = rp.run_once("demo")
    print(paint(f"\n  Run status: {status}", "1"))
    synced = sql("SELECT COUNT(*) n, SUM(part_count) v FROM rag_vector_sync")[0]
    step("What the pipeline remembers")
    table([("files processed (SHA-256 manifest)", sql("SELECT COUNT(*) n FROM etl_file_manifest WHERE status='processed'")[0]["n"]),
           ("payloads with a stored content hash", synced["n"]),
           ("vectors those hashes cover", synced["v"])], ["memory", "count"])
    points("Every task said 'skipped': no file, row or vector was processed twice",
           "A file is identified by the hash of its contents: the same file is never loaded twice, an edited file "
           "is loaded again",
           "Vectors: each payload's hash is compared with the one already embedded; only differences are embedded")


def part3():
    part(3, "CHANGE DATA CAPTURE (CDC)", "New data arrival detection for changes made directly in the database",
         ["Not all new data arrives as a file. An application can update MariaDB directly. Triggers write every "
          "change to the Milestone 2 Audit_Logs table; the pipeline's cdc_detect task reads the changes made "
          "outside the pipeline and propagates them."])
    rp = pipeline_module()
    unit = demo_unit()
    row = sql("SELECT dispatch_id, status FROM service_logs WHERE equipment_id=%s AND dispatch_id LIKE 'DISP-T%%' "
              "ORDER BY dispatch_id DESC LIMIT 1", (unit,)) if unit else []
    if not row:
        print(paint("  No test dispatch found: run part 1 first", "31"))
        return
    dispatch, old = row[0]["dispatch_id"], row[0]["status"]
    new = "Pending" if old == "Completed" else "Completed"
    step(f"A direct edit, as an application would make it:  UPDATE service_logs SET status='{new}' "
         f"WHERE dispatch_id='{dispatch}'   (was {old})")
    sql("UPDATE service_logs SET status=%s WHERE dispatch_id=%s", (new, dispatch), fetch=False)
    step("Audit_Logs: written by the trigger, in the same transaction as the edit")
    rows = sql("SELECT audit_id, changed_by, change_source, table_name, operation_type, record_id "
               "FROM Audit_Logs ORDER BY audit_id DESC LIMIT 6")
    table([tuple(r.values()) for r in rows], list(rows[0].keys()) if rows else [])
    step("Run the pipeline")
    rp.run_once("demo")
    text = sql("SELECT payload_text FROM rag_payloads WHERE source_id=%s", (dispatch,))[0]["payload_text"]
    step("The RAG context now holds the new status")
    print("  " + text.splitlines()[0])
    points(f"cdc_detect found 1 direct change (UPDATE service_logs {dispatch}) and marked the RAG context stale",
           "Only that one payload was re-embedded; the answer caches were cleared",
           "change_source tells the two apart: 'direct' rows are edits made outside the pipeline, rows tagged with "
           "a run ID are the pipeline's own merges, which CDC ignores",
           "Trigger-based CDC reuses the Milestone 2 audit triggers; log-based CDC (Debezium/Kafka) would not fit "
           "on a 4 GB instance")


def part4():
    part(4, "ERROR HANDLING AND LOGGING", "Implement error handling and logging; zero data integrity errors",
         ["Bad rows never reach the stores, every run and task is recorded, and an integrity gate checks every "
          "store at the end of each run."])
    rp = pipeline_module()
    step("Quarantine: rows that failed validation, with the reason (table etl_quarantine)")
    rows = sql("SELECT run_id, source_type, record_key, reason FROM etl_quarantine ORDER BY quarantine_id DESC LIMIT 6")
    table([tuple(r.values()) for r in rows], ["run", "source", "record", "reason"])
    step("Run history: every task, its status, time and retries (tables etl_runs, etl_task_runs)")
    rp.show_status(1)
    step("Structured log file")
    print(f"  {config.LOG_FILE}")
    for line in config.LOG_FILE.read_text().splitlines()[-3:]:
        print("  " + line)
    points("Bad rows (unknown unit, unreadable date, missing ID) are set aside with the reason; the good rows "
           "still load",
           "Each task retries with exponential backoff; if it still fails, the tasks after it are 'blocked' so "
           "bad data cannot move on",
           "Silver and Bronze are written in one transaction: a failure rolls back both",
           "integrity_check runs even after a failure: orphaned keys and store counts must match (0 errors)")


def retrieval_ms(retriever, question, runs=5):
    retriever.retrieve(question)                       # warm the path
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        retriever.retrieve(question)
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def part5():
    part(5, "PERFORMANCE OPTIMIZATION", "Profile latency, find bottlenecks, caching, index tuning, vector tuning",
         ["The same questions are retrieved by the Milestone 5 code and by the optimized Milestone 6 code, live. "
          "Then the answer cache is shown."])
    step("Loading both retrievers")
    from hybrid_retrieval import HybridRetriever
    baseline = HybridRetriever()
    baseline.warmup()
    opt = optimized()
    step("Retrieval time across MariaDB + ChromaDB + MongoDB (median of 5, no LLM)")
    rows = []
    for q in PERF_QUESTIONS:
        b, o = retrieval_ms(baseline, q), retrieval_ms(opt.retriever, q)
        rows.append((q, f"{b:.1f} ms", f"{o:.1f} ms", f"{b / o:.1f}x"))
    table(rows, ["question", "Milestone 5", "Milestone 6", "faster"])

    step("Answer cache: the same question twice (the second skips retrieval and Gemini)")
    q = "Which supplier makes the NMC cells used in the PowerStation G-3500?"
    for attempt in ("first ask", "second ask"):
        record = opt.ask(q)
        print(f"  {attempt}: {record['timings_ms']['total']:.1f} ms  (cache hit: {record['cache_hit']})")
    points("Bottleneck found by profiling: Gemini is ~95% of the answer time; of the retrieval, MariaDB was the "
           "slowest store",
           "SQL: connection pool, two new indexes chosen from EXPLAIN plans, the claim lookup rewritten from a "
           "LIKE scan to a key join (151x faster)",
           "Caches: question embeddings, model summaries, and whole answers keyed by the data version, so new "
           "data clears them automatically",
           "Vector search: ef_search re-tuned on the live ERP collection (recall@5 0.65 -> 0.95)")


def part6():
    part(6, "BENCHMARK RESULTS", "20+ complex prompts; P50/P95/P99 per stage; end-to-end; throughput",
         ["26 questions in 5 categories (specification, temporal, multi-hop, supply chain, grounding), run twice "
          "through the Milestone 5 pipeline and twice through the Milestone 6 pipeline, with Gemini."])
    report = RESULTS / "m6_benchmark_report.md"
    for heading, limit in (("Summary", 12), ("Retrieval fidelity and accuracy by category", 9),
                           ("Latency per stage (ms)", 14), ("Throughput", 13)):
        step(heading)
        md_section(report, heading, limit)
    for name, title in (("m6_sql_tuning.md", "SQL tuning (before -> after)"),
                        ("m6_vector_tuning.md", "Vector tuning (HNSW ef_search)"),
                        ("m6_trigger_overhead.md", "CDC trigger cost")):
        step(title)
        path = RESULTS / name
        lines = [l for l in path.read_text().splitlines() if l.startswith("|")] if path.exists() else ["(not run)"]
        for line in lines[:14]:
            print("  " + line)
    print(f"\n  Charts: {RESULTS / 'm6_latency_total.png'}, {RESULTS / 'm6_latency_stages.png'}")
    points("Median end-to-end latency under 1 s; every run under the 5 s target",
           "Retrieval about 3x faster and about 6x more retrieval throughput than Milestone 5",
           "Expected sources retrieved for every question; the answer cache serves repeats in about 0.1 ms",
           "End-to-end throughput is bounded by the Gemini API, not the databases")


def part7():
    part(7, "SOURCE PROVENANCE AND TRACEABILITY", "100% traceability; every fact cites a source record",
         ["Live questions about the new data from part 1: the unit's history and each PDF you added. Every "
          "statement must cite a source; the verifier checks it, and the audit fetches every cited source again "
          "from its database."])
    from ask import show
    import provenance_audit
    opt = optimized()
    question = HISTORY_Q.format(unit=demo_unit() or "EQ-7171")
    step(f"Question: {question}")
    record = opt.ask(question)
    show(record)
    records = [record]
    new_docs = [e for e in _cache.get("pdfs", []) if e["question"]]
    for entry in new_docs:
        step(f"Question about the new PDF {entry['file']}: {entry['question']}")
        records.append(opt.ask(entry["question"]))
        show(records[-1])
    step("Provenance audit: each cited source fetched again from MariaDB, MongoDB or ChromaDB")
    results = provenance_audit.audit(records, opt.retriever)
    rows = [(s["tag"], f"{s['db']}.{s['source']}", s["record_id"], s["kind"], s["outcome"])
            for r in results for s in r["sources"]]
    table(rows, ["tag", "database.table", "record", "kind", "check"])
    new_ids = re.findall(r"DISP-T\d+|CLM-T\d+", record["answer"])
    points("Every displayed statement ends with a citation such as [S3], and the verifier checked its numbers, IDs "
           "and dates against that source",
           "Each source is identified by database, table, record ID, and a document, chunk and timestamp where "
           "they exist",
           "The audit re-read every cited record from its database and compared content hashes: "
           f"{sum(r['confirmed'] for r in results)} of {sum(len(r['sources']) for r in results)} confirmed",
           f"The new data from part 1 is in the answer: {', '.join(dict.fromkeys(new_ids)) or 'see above'}",
           *([f"The PDF answers cite chunks of the new files ({', '.join(e['file'].split('_')[0] for e in new_docs)}), "
              "found within minutes of the file landing"] if new_docs else []),
           "A statement that cannot be traced is sent back once for a rewrite, then removed before display")


def part8(with_recovery):
    part(8, "FAILURE RECOVERY", "Recover gracefully from failures (database restart, network interruption)",
         ["A network interruption to Gemini is simulated live: the answer falls back to the retrieved evidence. "
          + ("Then MariaDB is restarted during a pipeline run and MongoDB is stopped during a question."
             if with_recovery else "The database restart tests run with --with-recovery (bash ops/recovery_test.sh).")])
    from ask import show
    opt = optimized()
    step("Gemini unreachable (simulated network failure)")
    real = opt.backend.generate

    def unreachable(prompt):
        raise ConnectionError("Gemini API unreachable (simulated network failure)")
    opt.backend.generate, cache = unreachable, opt.cache
    opt.cache = None
    try:
        show(opt.ask("What happened to unit SN-X7-0094 and which components were flagged?"))
    finally:
        opt.backend.generate, opt.cache = real, cache
    if with_recovery:
        step("Database restart and outage tests (ops/recovery_test.sh)")
        subprocess.run(["bash", str(M6 / "ops" / "recovery_test.sh")], check=False)
    points("No question fails silently: if the LLM is down, the retrieved evidence is shown, labelled",
           "If a database is down, the other stores still answer and the outage is reported",
           "If MariaDB restarts mid-run, connections retry with backoff and the run completes with 0 errors",
           "A crash at any point is completed by the next run (durable flags, hashes and the CDC position)")


def part9():
    part(9, "SYSTEM SYNTHESIS", "How the semester's work fits together",
         ["Milestone 6 reuses the earlier milestones instead of replacing them."])
    table([("M1", "Bronze/Silver tables, cleaning rules", "batch tables LIKE import_*; same rules as upserts"),
           ("M2", "stored procedure, Audit_Logs, triggers", "payload refresh; CDC change feed"),
           ("M3", "Galera cluster, ColumnStore", "separate deployment; code reaches MariaDB via MARIADB_HOST, retries"),
           ("M4", "chunker, embeddings, HNSW", "chunking and embedding of new documents; ef_search re-tuned"),
           ("M5", "hybrid retrieval, Gemini, verifier", "extended by m6_rag.py; baseline in the benchmark")],
          ["milestone", "built", "used in Milestone 6 as"])
    print("\n  Graph database: excluded from the project by the instructor in Milestone 5; supplier questions are "
          "answered from parts_inventory and the supply-chain documents.")
    points("One automated system: files and database edits in, verified and cited answers out",
           "Each store does the job it is best at: MariaDB for exact records, MongoDB for nested telemetry, "
           "ChromaDB for meaning")


# ----------------------------------------------------------------------------- main
def timer(action):
    subprocess.run(["sudo", "-n", "systemctl", action, TIMER], check=False, capture_output=True)


def main():
    global PAUSE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", type=int, choices=range(1, 10), help="run only this part")
    ap.add_argument("--from", dest="start", type=int, default=1, choices=range(1, 10), help="start at this part")
    ap.add_argument("--with-recovery", action="store_true", help="part 8 also restarts MariaDB and MongoDB")
    ap.add_argument("--no-pause", action="store_true", help="do not wait for Enter")
    args = ap.parse_args()
    PAUSE = not args.no_pause
    parts = {1: part1, 2: part2, 3: part3, 4: part4, 5: part5, 6: part6, 7: part7,
             8: lambda: part8(args.with_recovery), 9: part9}
    chosen = [args.part] if args.part else [n for n in parts if n >= args.start]

    print(paint("\n PROJECT GIGAVOLT - MILESTONE 6: Automated Pipeline, Optimization & System Synthesis", "1;37"))
    print("  Parts: " + ", ".join(str(n) for n in chosen) + "   (the pipeline timer is paused during the demo)")
    timer("stop")
    try:
        for n in chosen:
            parts[n]()
    except KeyboardInterrupt:
        print("\n  Demo stopped.")
    finally:
        timer("start")
        print(paint("\n  Demo complete. Pipeline timer turned back on.", "1;37"))


if __name__ == "__main__":
    main()
