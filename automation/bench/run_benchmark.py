#!/usr/bin/env python3
"""
run_benchmark.py - before/after benchmark of the RAG system.

For every question in questions.json it measures, for the Milestone 5 pipeline ("baseline") and
the optimized pipeline ("optimized"):
  - retrieval fidelity   were the expected source records retrieved?
  - answer accuracy      does the answer contain the expected facts? (some facts are computed from
                         the live databases, so they stay correct after new data arrives)
  - provenance           share of displayed factual statements traced to a cited source, and
                         every cited source re-checked against its database (provenance_audit.py)
  - latency              P50 / P95 / P99 for every pipeline stage and end to end
  - throughput           queries per second: end to end, retrieval only at 1/4/8 concurrent
                         clients, and repeated questions served from the answer cache

Outputs in results/:
    m6_benchmark_report.md     all tables            m6_runs.csv              one row per run
    m6_provenance_audit.md     the provenance audit  m6_answers.md            every answer with its sources
    m6_latency_total.png, m6_latency_stages.png      charts

Usage (on EC2, config.env loaded):
    python run_benchmark.py                       # both pipelines, 2 rounds
    python run_benchmark.py --only optimized --repeat 1 --ids S1,T2
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rag"))
from m6_rag import OptimizedRagPipeline  # noqa: E402
from rag_pipeline import RagPipeline, source_line  # noqa: E402
import provenance_audit  # noqa: E402

OUT = Path(os.environ.get("BENCH_RESULTS", HERE.parent / "results"))
STAGES = ["route", "resolve", "encode", "sql", "vector", "mongo", "retrieve_parallel", "assemble", "generate", "verify", "total"]
LABELS = {"route": "Route", "resolve": "Resolve unit", "encode": "Embed question", "sql": "MariaDB", "vector": "ChromaDB",
          "mongo": "MongoDB", "retrieve_parallel": "All retrieval (parallel)", "assemble": "Assemble context",
          "generate": "LLM generation", "verify": "Verify", "total": "Total"}
TARGET_MS = 5000
ABSTAIN_RE = re.compile(r"(do(es)? not|don't|no) (show|contain|include|have|record|mention)|not available|no (information|record)", re.I)
COLORS = {"baseline": "#2a78d6", "optimized": "#eb6834"}


def squash(text):
    return re.sub(r"[\s,]", "", str(text)).lower()


def resolve_truth(questions):
    """Fills in the expected facts that are computed from the live databases."""
    import pymysql
    from pymongo import MongoClient
    conn = pymysql.connect(host=os.environ.get("MARIADB_HOST", "127.0.0.1"), port=int(os.environ.get("MARIADB_PORT", 3306)),
                           user=os.environ["MARIADB_USER"], password=os.environ["MARIADB_PASSWORD"],
                           database=os.environ.get("MARIADB_DB", "gigavolt_erp"))
    mongo = MongoClient(os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017"))[os.environ.get("MONGO_DB", "gigavolt_iot")]
    for q in questions:
        facts = list(q.get("facts", []))
        if q.get("truth_sql"):
            with conn.cursor() as cur:
                cur.execute(q["truth_sql"])
                facts += [str(v) for row in cur.fetchall() for v in row if v is not None]
        if q.get("truth_mongo"):
            spec = q["truth_mongo"]
            flt = json.loads(json.dumps(spec["filter"]))
            for op, value in list(flt.get("timestamp", {}).items()):
                flt["timestamp"][op] = datetime.fromisoformat(value)
            facts += sorted(str(v) for v in mongo["bms_telemetry"].distinct(spec["distinct"], flt))
        q["expected_facts"] = facts
    conn.close()
    return questions


def score(q, record):
    retrieved = [f"{s.get('record_id', '')} {s.get('doc', '')} {s.get('source', '')}" for s in record["sources"]]
    found = lambda key: any(key in r for r in retrieved)  # noqa: E731
    sources_ok = all(found(k) for k in q.get("sources_all", [])) and \
        (not q.get("sources_any") or any(found(k) for k in q["sources_any"]))
    answer = squash(record["answer"])
    facts = q.get("expected_facts", [])
    fact_hits = sum(1 for f in facts if squash(f) in answer)
    check = record["verification"]
    if q.get("abstain"):
        correct = bool(ABSTAIN_RE.search(record["answer"])) and check["factual"] == 0
    else:
        correct = fact_hits == len(facts) and not record.get("llm_error")
    return {"retrieval_ok": sources_ok, "fact_hits": fact_hits, "fact_total": len(facts), "correct": correct,
            "supported": check["supported"], "factual": check["factual"]}


def percentiles(values):
    import numpy as np
    if not values:
        return None
    return tuple(np.percentile(values, [50, 95, 99]))


def run_mode(name, pipeline, questions, repeat, pause, rows, records):
    print(f"\n=== {name} ===")
    for r in range(repeat):
        for q in questions:
            record = pipeline.ask(q["question"])
            record["id"] = q["id"]
            s = score(q, record)
            t = record["timings_ms"]
            rows.append({"mode": name, "round": r + 1, "id": q["id"], "category": q["category"], **s,
                         "regenerated": record.get("regenerated", False), "llm_calls": record.get("llm_calls", 1),
                         "removed": len(record.get("removed_statements", [])),
                         "llm_error": bool(record.get("llm_error")), "rate_limit_wait": t.get("rate_limit_wait", 0),
                         **{st: round(t[st], 1) for st in STAGES if st in t}, "answer": record["answer"]})
            records.setdefault(name, []).append(record)
            print(f"[{name} {r + 1}] {q['id']:<3} {t['total'] / 1000:5.2f}s  correct={s['correct']!s:<5} "
                  f"retrieved={s['retrieval_ok']!s:<5} facts={s['fact_hits']}/{s['fact_total']} "
                  f"traced={s['supported']}/{s['factual']}")
            time.sleep(pause)


def throughput(retriever, questions, levels=(1, 4, 8)):
    """Retrieval-only queries per second (no LLM), at several numbers of concurrent clients."""
    out = {}
    texts = [q["question"] for q in questions] * 2
    for workers in levels:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(retriever.retrieve, texts))
        out[workers] = len(texts) / (time.perf_counter() - start)
    return out


def cached_run(pipeline, questions, pause):
    """Answers each question once (filling the cache), then measures repeated questions."""
    for q in questions:
        if not pipeline.ask(q["question"]).get("cache_hit"):
            time.sleep(pause)
    times = []
    start = time.perf_counter()
    for _ in range(5):
        for q in questions:
            times.append(pipeline.ask(q["question"])["timings_ms"]["total"])
    return len(times) / (time.perf_counter() - start), percentiles(times), pipeline.cache.hits, pipeline.cache.misses


def summarize(rows, mode):
    sel = [r for r in rows if r["mode"] == mode]
    clean = [r for r in sel if not r["llm_error"] and not r["rate_limit_wait"]]
    stats = {st: percentiles([r[st] for r in clean if r.get(st) is not None]) for st in STAGES}
    totals = [r["total"] for r in clean]
    return {"n": len(sel), "clean": len(clean), "stats": stats,
            "under_target": sum(1 for t in totals if t < TARGET_MS),
            "qps": 1000 * len(totals) / sum(totals) if totals else 0,
            "correct": sum(r["correct"] for r in sel), "retrieval": sum(r["retrieval_ok"] for r in sel),
            "traced": (sum(r["supported"] for r in sel), sum(r["factual"] for r in sel)),
            "regenerated": sum(r["regenerated"] for r in sel), "removed": sum(r["removed"] for r in sel),
            "by_category": {c: (sum(r["correct"] for r in sel if r["category"] == c),
                                sum(r["retrieval_ok"] for r in sel if r["category"] == c),
                                sum(1 for r in sel if r["category"] == c),
                                percentiles([r["total"] for r in clean if r["category"] == c]))
                            for c in dict.fromkeys(r["category"] for r in sel)}}


def charts(summaries):
    """Two single-axis charts: end-to-end percentiles (seconds), and the retrieval stages (milliseconds)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    modes = list(summaries)
    ink, muted, grid = "#1f1f1d", "#6b6a63", "#e6e5df"
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": grid, "axes.labelcolor": muted, "xtick.color": muted,
                         "ytick.color": muted, "axes.spines.top": False, "axes.spines.right": False})

    def grouped(ax, groups, values, unit):
        width = 0.8 / len(modes)
        for i, m in enumerate(modes):
            xs = [x + i * width for x in range(len(groups))]
            bars = ax.bar(xs, values[m], width * 0.92, color=COLORS.get(m, "#6250d6"), label=m.capitalize())
            for bar, v in zip(bars, values[m]):
                ax.annotate(f"{v:.2f}" if unit == "s" else f"{v:.1f}", (bar.get_x() + bar.get_width() / 2, v),
                            ha="center", va="bottom", fontsize=8, color=ink, xytext=(0, 2), textcoords="offset points")
        ax.set_xticks([x + width * (len(modes) - 1) / 2 for x in range(len(groups))], groups)
        ax.yaxis.grid(True, color=grid, linewidth=0.8)
        ax.set_axisbelow(True)
        if len(modes) > 1:
            ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=len(modes))

    fig, ax = plt.subplots(figsize=(7, 3.8))
    grouped(ax, ["P50", "P95", "P99"], {m: [v / 1000 for v in summaries[m]["stats"]["total"]] for m in modes}, "s")
    ax.axhline(TARGET_MS / 1000, color=muted, linewidth=1, linestyle="--")
    ax.annotate("5 s target", (2.75, TARGET_MS / 1000), ha="right", va="bottom", fontsize=8, color=muted)
    ax.set_ylabel("seconds")
    ax.set_title("End-to-end latency, question to verified answer", loc="left", color=ink, fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "m6_latency_total.png", dpi=160)

    stages = [s for s in ("encode", "sql", "vector", "mongo", "retrieve_parallel") if all(summaries[m]["stats"].get(s) for m in modes)]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    grouped(ax, [LABELS[s].replace(" (parallel)", "\n(parallel)") for s in stages],
            {m: [summaries[m]["stats"][s][0] for s in stages] for m in modes}, "ms")
    ax.set_ylabel("milliseconds (P50)")
    ax.set_title("Median time of the retrieval stages", loc="left", color=ink, fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "m6_latency_stages.png", dpi=160)


def write_outputs(rows, summaries, qps, cached, questions, repeat, records, audit_summary):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "m6_runs.csv").open("w", newline="") as fh:
        keys = sorted({k for r in rows for k in r if k != "answer"}) + ["answer"]
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    modes = list(summaries)
    head = lambda first: [f"| {first} | " + " | ".join(modes) + " |", "|---|" + "---:|" * len(modes)]  # noqa: E731
    L = ["# Milestone 6 benchmark report", "",
         f"{len(questions)} questions x {repeat} round(s) per pipeline, run {datetime.now():%Y-%m-%d %H:%M}. "
         "'baseline' is the Milestone 5 pipeline; 'optimized' is the Milestone 6 pipeline with its answer cache "
         "switched off, so these are uncached numbers. Percentiles exclude runs that hit an LLM error or a "
         "rate-limit wait (counted below).", "", "## Summary", ""] + head("Measure")

    def row(label, fn):
        L.append(f"| {label} | " + " | ".join(fn(summaries[m]) for m in modes) + " |")
    row("Median end-to-end latency (target < 5 s)", lambda s: f"{s['stats']['total'][0] / 1000:.2f} s" if s["stats"]["total"] else "-")
    row("Runs under 5 s", lambda s: f"{s['under_target']}/{s['clean']}")
    row("Correct answers (all expected facts present)", lambda s: f"{s['correct']}/{s['n']} ({100 * s['correct'] / s['n']:.0f}%)")
    row("Expected sources retrieved", lambda s: f"{s['retrieval']}/{s['n']} ({100 * s['retrieval'] / s['n']:.0f}%)")
    row("Displayed statements traced to a source",
        lambda s: f"{s['traced'][0]}/{s['traced'][1]} ({100 * s['traced'][0] / max(s['traced'][1], 1):.1f}%)")
    row("Answers regenerated after a verifier flag", lambda s: str(s["regenerated"]))
    row("Untraceable statements removed before display", lambda s: str(s["removed"]))
    row("Runs excluded from percentiles (LLM error or rate-limit wait)", lambda s: str(s["n"] - s["clean"]))
    if audit_summary:
        L += ["", audit_summary]

    L += ["", "## Retrieval fidelity and accuracy by category", "",
          "| Category | " + " | ".join(f"{m} correct | {m} sources retrieved | {m} median (s)" for m in modes) + " |",
          "|---|" + "---:|" * (3 * len(modes))]
    for cat in summaries[modes[0]]["by_category"]:
        cells = []
        for m in modes:
            c, r, n, p = summaries[m]["by_category"].get(cat, (0, 0, 0, None))
            cells += [f"{c}/{n}", f"{r}/{n}", f"{p[0] / 1000:.2f}" if p else "-"]
        L.append(f"| {cat} | " + " | ".join(cells) + " |")

    L += ["", "## Latency per stage (ms)", "",
          "| Stage | " + " | ".join(f"{m} P50 | {m} P95 | {m} P99" for m in modes) + " |", "|---|" + "---:|" * (3 * len(modes))]
    for st in STAGES:
        cells = []
        for m in modes:
            p = summaries[m]["stats"].get(st)
            cells += [f"{v:.1f}" for v in p] if p else ["-"] * 3
        L.append(f"| {LABELS[st]} | " + " | ".join(cells) + " |")
    L += ["", "MariaDB, ChromaDB and MongoDB run in parallel, so 'All retrieval' is close to the slowest of the three, "
          "not their sum. 'LLM generation' includes the second call when an answer was regenerated.",
          "", "![End-to-end latency](m6_latency_total.png)", "", "![Retrieval stages](m6_latency_stages.png)"]

    L += ["", "## Throughput", "", "| Workload | Queries per second |", "|---|---:|"]
    for m in modes:
        L.append(f"| End to end with the LLM, one client, {m} | {summaries[m]['qps']:.2f} |")
    for mode, levels in qps.items():
        for workers, value in levels.items():
            L.append(f"| Retrieval only (no LLM), {mode}, {workers} concurrent client(s) | {value:.1f} |")
    if cached:
        rate, p, hits, misses = cached
        L.append(f"| Repeated questions served from the answer cache | {rate:.0f} |")
        L += ["", f"Answer cache: {hits} hits, {misses} misses; a cached answer takes P50 {p[0]:.3f} ms, P95 {p[1]:.3f} ms, "
              f"P99 {p[2]:.3f} ms."]
    L += ["", "End-to-end throughput is bounded by the LLM API (one call per question, and the free tier's "
          "requests-per-minute limit), not by the databases, which is why retrieval-only throughput is reported separately."]

    L += ["", "## Per question (optimized, first round)" if "optimized" in modes else "## Per question (first round)", "",
          "| ID | Category | Question | Total (s) | Correct | Sources | Traced |", "|---|---|---|---:|---|---|---:|"]
    last = modes[-1]
    text = {q["id"]: q["question"] for q in questions}
    for r in rows:
        if r["mode"] == last and r["round"] == 1:
            L.append(f"| {r['id']} | {r['category']} | {text[r['id']]} | {r['total'] / 1000:.2f} | "
                     f"{'yes' if r['correct'] else 'NO'} | {'yes' if r['retrieval_ok'] else 'NO'} | {r['supported']}/{r['factual']} |")
    (OUT / "m6_benchmark_report.md").write_text("\n".join(L) + "\n")

    A = ["# Benchmark answers with source provenance", ""]
    for record in records.get(last, [])[:len(questions)]:
        A += [f"## {record['id']}: {record['question']}", "", record["answer"], "", "| Tag | Source |", "|---|---|"]
        A += [f"| {s['tag']} | {source_line(s)} |" for s in record["sources"] if s["cited"]]
        check = record["verification"]
        A += ["", f"Provenance check: {check['supported']}/{check['factual']} factual statements traced. "
              f"Latency {record['timings_ms']['total'] / 1000:.2f} s.", ""]
    (OUT / "m6_answers.md").write_text("\n".join(A))
    try:
        charts(summaries)
    except Exception as exc:  # noqa: BLE001
        print(f"charts skipped: {exc}")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--pause", type=float, default=5.0, help="seconds between LLM calls (free-tier rate limit)")
    ap.add_argument("--only", choices=["baseline", "optimized"])
    ap.add_argument("--ids", help="comma-separated question IDs to run")
    args = ap.parse_args()

    questions = json.loads((HERE / "questions.json").read_text())["questions"]
    if args.ids:
        wanted = set(args.ids.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    resolve_truth(questions)
    rows, summaries, qps, records = [], {}, {}, {}
    if args.only != "optimized":
        base = RagPipeline()
        base.retriever.warmup()
        run_mode("baseline", base, questions, args.repeat, args.pause, rows, records)
        summaries["baseline"] = summarize(rows, "baseline")
        qps["baseline"] = throughput(base.retriever, questions)
    cached = audit_summary = None
    if args.only != "baseline":
        optimized = OptimizedRagPipeline(answer_cache=False)     # uncached numbers: a cache hit would hide real latency
        optimized.retriever.warmup()
        run_mode("optimized", optimized, questions, args.repeat, args.pause, rows, records)
        summaries["optimized"] = summarize(rows, "optimized")
        qps["optimized"] = throughput(optimized.retriever, questions)

        results = provenance_audit.audit(records["optimized"], optimized.retriever)
        text, ok = provenance_audit.report(results, OUT / "m6_provenance_audit.md")
        cited = sum(len(r["sources"]) for r in results)
        audit_summary = (f"Provenance audit of the optimized answers: {sum(r['confirmed'] for r in results)} of {cited} cited "
                         f"sources were fetched again from their database and confirmed; "
                         f"{'every answer is fully traceable' if ok else 'NOT every answer is fully traceable'} "
                         "(details in m6_provenance_audit.md).")

        cached_pipeline = OptimizedRagPipeline(answer_cache=True, backend=optimized.backend, retriever=optimized.retriever)
        cached = cached_run(cached_pipeline, questions, args.pause)
    write_outputs(rows, summaries, qps, cached, questions, args.repeat, records, audit_summary)


if __name__ == "__main__":
    main()
