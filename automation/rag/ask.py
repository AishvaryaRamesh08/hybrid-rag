#!/usr/bin/env python3
"""
ask.py - ask the optimized pipeline questions from the command line.

    python ask.py "question"                    # one question
    python ask.py                               # interactive loop (shows cache hits on repeats)
    python ask.py --simulate-llm-outage "q"     # Gemini made unreachable, to show the fallback
"""
import argparse

from m6_rag import OptimizedRagPipeline
from rag_pipeline import print_record


def show(record):
    if record.get("cache_hit"):
        print(f"\n(answer cache hit: {record['timings_ms']['total']:.1f} ms, retrieval and Gemini skipped)")
    print_record(record)
    if record.get("regenerated"):
        print("NOTE: the answer was regenerated once after the verifier flagged a statement")
    for statement in record.get("removed_statements", []):
        print(f"REMOVED (could not be traced to a source): {statement[:120]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?")
    ap.add_argument("--simulate-llm-outage", action="store_true")
    args = ap.parse_args()
    pipeline = OptimizedRagPipeline()
    if args.simulate_llm_outage:
        def unreachable(prompt):
            raise ConnectionError("Gemini API unreachable (simulated network failure)")
        pipeline.backend.generate = unreachable
    pipeline.retriever.warmup()
    if args.question:
        show(pipeline.ask(args.question))
        return
    while True:
        try:
            question = input("\nQuestion (or 'quit'): ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("quit", "exit", "q"):
            break
        if question:
            show(pipeline.ask(question))


if __name__ == "__main__":
    main()
