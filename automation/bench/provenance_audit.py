#!/usr/bin/env python3
"""
provenance_audit.py - automated source provenance audit.

The answer-time verifier (verify_answer) checks every statement against the evidence it cites.
This audit goes one step further and checks the evidence against the databases:

  for every source cited by an answer
      record     (a payload, a telemetry reading, a document chunk)
                 -> fetched again from its database BY ID; its text must hash to the same
                    value that was hashed when the answer was written
      derived    (an aggregate such as "fleet by status", or a "no record exists" result)
                 -> the retrieval is executed again and must return the same text

An answer passes when every factual statement is supported by its citations AND every cited
source is confirmed in its database. Any other outcome is listed by name.

Used by run_benchmark.py, and on its own against the audit trail of live questions:
    python provenance_audit.py [--last 20]     # audits logs/rag_audit.jsonl -> results/m6_provenance_audit.md
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rag"))
from m6_rag import AUDIT_LOG, OptimizedHybridRetriever, text_hash  # noqa: E402

OUT = Path(os.environ.get("BENCH_RESULTS", HERE.parent / "results"))


def is_derived(source):
    return source["record_id"].startswith(("aggregate:", "lookup:")) or source["source"] == "equipment_units"


def check_record(retriever, source):
    """Fetch one cited record from its database by ID and compare content hashes."""
    db, record_id = source["db"], source["record_id"]
    if db == "mariadb":
        rows = retriever.sql._rows("SELECT payload_text FROM rag_payloads WHERE source_table IN "
                                   "('service_logs','warranty_claims') AND source_id=%s", (record_id,))
        texts = [r["payload_text"] for r in rows]
    elif db == "mongodb":
        doc = retriever.document.col.find_one({"_id": record_id})
        texts = [retriever.document.reading_text(doc)] if doc else []
    else:
        collection = retriever.vector.manuals if source["source"] == "gv_manuals" else retriever.vector.erp
        texts = collection.get(ids=[source.get("chunk", record_id)], include=["documents"])["documents"]
    if not texts:
        return "missing"
    return "confirmed" if source["text_sha"] in {text_hash(t) for t in texts} else "changed"


def audit_record(retriever, record):
    """Returns one row per cited source, with the outcome of its database check."""
    cited = [s for s in record["sources"] if s["cited"]]
    rederived = None
    rows = []
    for source in cited:
        if is_derived(source):
            if rederived is None:           # run the same retrieval again, once per answer
                result = retriever.retrieve(record["question"])
                rederived = {s.record_id: text_hash(s.text) for items in result.snippets.values() for s in items}
            found = rederived.get(source["record_id"])
            outcome = "confirmed" if found == source["text_sha"] else ("missing" if found is None else "changed")
            kind = "derived"
        else:
            outcome, kind = check_record(retriever, source), "record"
        rows.append({**source, "kind": kind, "outcome": outcome})
    return rows


def audit(records, retriever=None):
    retriever = retriever or OptimizedHybridRetriever()
    results = []
    for record in records:
        if record.get("llm_error"):
            continue
        sources = audit_record(retriever, record)
        check = record["verification"]
        results.append({"question": record["question"], "id": record.get("id", ""), "factual": check["factual"],
                        "supported": check["supported"], "sources": sources,
                        "confirmed": sum(1 for s in sources if s["outcome"] == "confirmed"),
                        "removed": record.get("removed_statements", []), "regenerated": record.get("regenerated", False),
                        "statements": check["statements"], "data_version": record.get("data_version", "")})
    return results


def where(source):
    parts = [f"{source['db']}.{source['source']}", source["record_id"]]
    if source.get("doc"):
        parts.append(f"{source['doc']} p.{source.get('page')}")
    if source.get("chunk") and source["chunk"] != source["record_id"]:
        parts.append(f"chunk {source['chunk']}")
    parts.append(source.get("timestamp") or f"retrieved {source['retrieved_at']}")
    return " | ".join(parts)


def report(results, path=None, examples=4):
    statements = sum(r["factual"] for r in results)
    supported = sum(r["supported"] for r in results)
    cited = sum(len(r["sources"]) for r in results)
    confirmed = sum(r["confirmed"] for r in results)
    passed = sum(1 for r in results if r["supported"] == r["factual"] and r["confirmed"] == len(r["sources"]))
    pct = lambda a, b: f"{100 * a / b:.1f}%" if b else "n/a"  # noqa: E731
    L = ["# Source provenance audit", "",
         "| Measure | Result |", "|---|---:|",
         f"| Answers audited | {len(results)} |",
         f"| Factual statements displayed | {statements} |",
         f"| Statements traced to a cited source (verifier) | {supported} ({pct(supported, statements)}) |",
         f"| Cited sources | {cited} |",
         f"| Cited sources confirmed in their database (this audit) | {confirmed} ({pct(confirmed, cited)}) |",
         f"| Answers fully traceable | {passed} of {len(results)} |",
         f"| Answers regenerated after a verifier flag | {sum(r['regenerated'] for r in results)} |",
         f"| Untraceable statements removed before display | {sum(len(r['removed']) for r in results)} |", "",
         "## Per answer", "", "| # | Question | Statements traced | Sources confirmed | Removed |", "|---|---|---:|---:|---:|"]
    for n, r in enumerate(results, start=1):
        L.append(f"| {r['id'] or n} | {r['question'][:90]} | {r['supported']}/{r['factual']} | "
                 f"{r['confirmed']}/{len(r['sources'])} | {len(r['removed'])} |")
    failures = [(r, s) for r in results for s in r["sources"] if s["outcome"] != "confirmed"]
    L += ["", "## Sources that were not confirmed", ""]
    L += [f"- {r['id'] or r['question'][:40]}: {where(s)} -> {s['outcome']}" for r, s in failures] or ["None."]
    removed = [(r, text) for r in results for text in r["removed"]]
    L += ["", "## Statements removed because they could not be traced", ""]
    L += [f"- {r['id'] or r['question'][:40]}: {text[:200]}" for r, text in removed] or ["None."]
    L += ["", "## Statement-to-source traces (examples)", ""]
    for r in results[:examples]:
        by_tag = {s["tag"]: s for s in r["sources"]}
        L += [f"**{r['question']}**", ""]
        for item in r["statements"]:
            if item["verdict"] == "no_claim":
                continue
            L.append(f"- {item['statement'][:220]}")
            L += [f"    - [{tag}] {where(by_tag[tag])} -> {by_tag[tag]['outcome']} ({by_tag[tag]['kind']})"
                  for tag in item["cites"] if tag in by_tag]
        L.append("")
    text = "\n".join(L) + "\n"
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return text, passed == len(results)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--last", type=int, default=20, help="audit the last N answers in the audit trail")
    args = ap.parse_args()
    lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()[-args.last:]
    text, ok = report(audit([json.loads(line) for line in lines]), OUT / "m6_provenance_audit.md")
    print(text.split("## Per answer")[0])
    print(f"Full report: {OUT / 'm6_provenance_audit.md'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
