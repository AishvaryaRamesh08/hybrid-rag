#!/usr/bin/env python3
"""
tune_vector.py - speed/accuracy tuning of the HNSW search parameter on the LIVE collections.

Milestone 4 chose M=16, ef_construction=50, ef_search=25 on the document corpus alone. The
vector store now also holds 6,000+ ERP payloads, so the choice is re-checked here on both
collections, with the benchmark questions as queries.

For each ef_search value a temporary copy of the collection is built from the stored vectors
(nothing is re-embedded), because Chroma fixes ef_search when a collection is created
(a Milestone 4 finding). Each copy is measured for
    recall@5   against exact brute-force search over the same vectors. Ties count as hits:
               many ERP payloads share the same text template and therefore the same distance.
    latency    P50 and P95 of the search call
The temporary copies are deleted afterwards. The live collections are not modified.

Decision rule: per collection, take the smallest ef_search whose recall@5 is at least 0.95,
provided its P50 stays under 5 ms. --apply rebuilds a live collection with the chosen value from
its stored vectors, documents and metadata (again without re-embedding) and checks the count.

Output: printed, and written to results/m6_vector_tuning.md
Usage (on EC2, config.env loaded):
    python tune_vector.py [--ef 10,25,50,100,200,400]     # measure only
    python tune_vector.py --apply gv_erp:200              # rebuild gv_erp with ef_search=200
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pipeline"))
from config import chroma_client  # noqa: E402  (also puts the Milestone 4 modules on the path)
from embed import load_model  # noqa: E402
from vectordb import create_collection  # noqa: E402

OUT = Path(os.environ.get("BENCH_RESULTS", HERE.parent / "results"))
K, PASSES = 5, 5


def measure(col, queries, kth_distance):
    times, hits = [], 0
    for p in range(PASSES):
        for q, limit in zip(queries, kth_distance):
            start = time.perf_counter()
            result = col.query(query_embeddings=[q.tolist()], n_results=K, include=["distances"])
            times.append((time.perf_counter() - start) * 1000)
            if p == 0:
                hits += sum(1 for d in result["distances"][0] if d <= limit + 1e-4)
    return hits / (K * len(queries)), np.percentile(times, 50), np.percentile(times, 95)


def apply(name, ef):
    client = chroma_client()
    data = client.get_collection(name, embedding_function=None).get(include=["embeddings", "documents", "metadatas"])
    vectors = np.asarray(data["embeddings"], dtype=np.float32)
    col = create_collection(client, name, 16, 50, int(ef))          # drops and recreates the collection
    for start in range(0, len(vectors), 1000):
        end = start + 1000
        col.add(ids=data["ids"][start:end], embeddings=vectors[start:end].tolist(),
                documents=data["documents"][start:end], metadatas=data["metadatas"][start:end])
    if col.count() != len(data["ids"]):
        raise SystemExit(f"{name}: rebuilt with {col.count()} vectors, expected {len(data['ids'])}")
    print(f"{name} rebuilt with ef_search={ef}: {col.count()} vectors")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ef", default="10,25,50,100,200,400", help="ef_search values to compare")
    ap.add_argument("--apply", metavar="COLLECTION:EF", help="rebuild a live collection with this ef_search")
    args = ap.parse_args()
    if args.apply:
        return apply(*args.apply.split(":"))
    ef_values = [int(v) for v in args.ef.split(",")]

    questions = [q["question"] for q in json.loads((HERE / "questions.json").read_text())["questions"]]
    queries = load_model().encode(questions, normalize_embeddings=True).astype(np.float32)
    client = chroma_client()
    lines = ["# Vector search tuning (HNSW ef_search)", "",
             f"{len(questions)} benchmark questions as queries, k={K}, M=16, ef_construction=50. Recall is measured against "
             "exact search over the same vectors.", "",
             "| Collection | Vectors | ef_search | recall@5 | P50 (ms) | P95 (ms) |", "|---|---:|---:|---:|---:|---:|"]
    for name in ("gv_manuals", "gv_erp"):
        data = client.get_collection(name, embedding_function=None).get(include=["embeddings"])
        vectors = np.asarray(data["embeddings"], dtype=np.float32)
        distances = 1.0 - queries @ vectors.T                      # cosine distance; vectors are normalized
        kth_distance = np.sort(distances, axis=1)[:, K - 1]
        for ef in ef_values:
            temp = create_collection(client, f"tune_{name}_{ef}", 16, 50, ef)
            for start in range(0, len(vectors), 1000):
                temp.add(ids=data["ids"][start:start + 1000], embeddings=vectors[start:start + 1000].tolist())
            recall, p50, p95 = measure(temp, queries, kth_distance)
            client.delete_collection(temp.name)
            lines.append(f"| {name} | {len(vectors)} | {ef} | {recall:.3f} | {p50:.2f} | {p95:.2f} |")
            print(lines[-1])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "m6_vector_tuning.md").write_text("\n".join(lines) + "\n")
    print(f"\nWritten to {OUT / 'm6_vector_tuning.md'}")


if __name__ == "__main__":
    main()
