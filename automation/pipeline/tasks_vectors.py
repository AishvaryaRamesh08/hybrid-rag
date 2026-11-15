"""
tasks_vectors.py - incremental document chunking and vector re-indexing.

    chunk_documents   new or changed PDF/TXT files are copied to the manuals folder and chunked
    sync_documents    per document, only chunks whose text changed are embedded; chunks that
                      no longer exist are deleted from gv_manuals
    sync_erp_vectors  gv_erp is brought in line with rag_payloads. MariaDB keeps a hash of what
                      was embedded for every payload (rag_vector_sync); one SQL comparison returns
                      exactly the payloads that are new, changed or gone. Nothing else is embedded.

The ERP sync compares desired state with actual state instead of trusting what the current run
did, so it is safe to re-run after a crash at any point.
"""
import shutil
from datetime import datetime, timezone

from config import MANUALS, chroma_client, mariadb, now

BATCH = 500
HASH = "SHA2(CONCAT(p.payload_text, '|', COALESCE(p.metadata, '')), 256)"
ON_KEY = "s.source_table = p.source_table AND s.source_id = p.source_id"


def model(ctx):
    """The embedding model is loaded once per run, and only if something needs embedding."""
    if "embed_model" not in ctx:
        from embed import load_model
        ctx["embed_model"] = load_model()
    return ctx["embed_model"]


def embed(ctx, texts):
    from embed import embed_texts
    return embed_texts(texts, model(ctx), batch_size=16, verbose=False)


def upsert(col, ids, texts, metadatas, vectors):
    import numpy as np
    for start in range(0, len(ids), BATCH):
        end = start + BATCH
        col.upsert(ids=ids[start:end], documents=texts[start:end], metadatas=metadatas[start:end],
                   embeddings=np.asarray(vectors[start:end], dtype=np.float32).tolist())


def delete(col, ids):
    for start in range(0, len(ids), BATCH):
        col.delete(ids=ids[start:start + BATCH])


# ----------------------------------------------------------------------------- documents
def chunk_documents(ctx):
    files = [f for f in ctx["files"] if f["source"] == "document"]
    if not files:
        return {"status": "skipped", "message": "no new documents"}
    from chunker import ChunkConfig, chunk_file, make_token_counter

    cfg = ChunkConfig()
    count = make_token_counter(cfg.tokenizer_name)
    MANUALS.mkdir(parents=True, exist_ok=True)
    chunks_by_doc = {}
    for f in files:
        target = MANUALS / f["path"].name
        shutil.copy2(f["path"], target)
        try:
            chunks = chunk_file(target, cfg, count)
        except Exception as exc:  # noqa: BLE001 - one unreadable file must not stop the others
            chunks, reason = [], f"could not be read: {type(exc).__name__}: {str(exc)[:150]}"
        else:
            reason = "no text could be extracted"
        if not chunks:
            ctx["state"].quarantine(ctx["run_id"], "document", f["path"], None, reason, {"file": f["path"].name})
            ctx.setdefault("rejected", {})[str(f["path"])] = reason
            target.unlink(missing_ok=True)
            continue
        chunks_by_doc[chunks[0]["doc_id"]] = chunks
        ctx.setdefault("rows_by_file", {})[str(f["path"])] = len(chunks)
    ctx["doc_chunks"] = chunks_by_doc
    total = sum(len(c) for c in chunks_by_doc.values())
    return {"rows_in": len(files), "rows_out": total, "message": f"{total} chunks from {len(chunks_by_doc)} document(s)"}


def sync_documents(ctx):
    chunks_by_doc = ctx.get("doc_chunks") or {}
    if not chunks_by_doc:
        return {"status": "skipped", "message": "no document chunks to index"}
    from vectordb import chunk_metadata

    col = chroma_client().get_collection("gv_manuals", embedding_function=None)
    stamp = datetime.now(timezone.utc)
    embedded = kept = removed = 0
    for doc_id, chunks in chunks_by_doc.items():
        old = col.get(where={"doc_id": doc_id}, include=["documents"])
        old_text = dict(zip(old["ids"], old["documents"]))
        changed = [c for c in chunks if old_text.get(c["id"]) != c["text"]]
        gone = [i for i in old_text if i not in {c["id"] for c in chunks}]
        if changed:
            vectors = embed(ctx, [c["embed_text"] for c in changed])
            upsert(col, [c["id"] for c in changed], [c["text"] for c in changed],
                   [chunk_metadata(c, int(stamp.timestamp()), stamp.isoformat(timespec="seconds")) for c in changed],
                   vectors)
        delete(col, gone)
        embedded += len(changed)
        kept += len(chunks) - len(changed)
        removed += len(gone)
    ctx["vectors_changed"] = ctx.get("vectors_changed", 0) + embedded + removed
    return {"rows_in": embedded + kept, "rows_out": embedded,
            "message": f"{embedded} chunks embedded, {kept} unchanged, {removed} removed; gv_manuals now {col.count()}"}


# ----------------------------------------------------------------------------- ERP payloads
def part_ids(source_table, source_id, part_count):
    return [f"{source_table}:{source_id}::p{n}" for n in range(1, part_count + 1)]


def bootstrap(ctx, conn, col, count_tokens, limit):
    """First run only: gv_erp was built in Milestone 5, before rag_vector_sync existed.
    Payloads whose stored vectors already match are recorded as synced, so they are not embedded again."""
    from build_vectors import payload_items

    with conn.cursor() as cur:
        cur.execute(f"SELECT p.payload_id, p.source_table, p.source_id, p.payload_text, p.metadata, {HASH} h "
                    "FROM rag_payloads p")
        rows = cur.fetchall()
    existing = col.get(include=["documents"])
    stored = dict(zip(existing["ids"], existing["documents"]))
    synced, wanted_ids = [], set()
    for row in rows:
        items = payload_items([row], count_tokens, limit, "")
        if all(stored.get(item["id"]) == item["text"] for item in items):
            synced.append((row["source_table"], row["source_id"], row["h"], len(items), now(), "bootstrap"))
            wanted_ids.update(item["id"] for item in items)
    delete(col, [i for i in stored if i not in wanted_ids])     # vectors with no matching payload
    with conn.cursor() as cur:
        cur.executemany("REPLACE INTO rag_vector_sync VALUES (%s,%s,%s,%s,%s,%s)", synced)
    return len(synced)


def sync_erp_vectors(ctx):
    conn = mariadb()
    try:
        col = chroma_client().get_collection("gv_erp", embedding_function=None)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM rag_vector_sync")
            first_run = cur.fetchone()["n"] == 0 and col.count() > 0
            if not first_run:       # cheap check first: the model is only loaded when there is work
                cur.execute(f"SELECT (SELECT COUNT(*) FROM rag_payloads p LEFT JOIN rag_vector_sync s ON {ON_KEY} "
                            f"WHERE s.source_id IS NULL OR s.content_hash <> {HASH}) changed, "
                            f"(SELECT COUNT(*) FROM rag_vector_sync s LEFT JOIN rag_payloads p ON {ON_KEY} "
                            "WHERE p.source_id IS NULL) gone")
                pending = cur.fetchone()
                if not pending["changed"] and not pending["gone"]:
                    return {"status": "skipped", "message": f"gv_erp already in sync ({col.count()} vectors)"}

        from build_vectors import payload_items
        m = model(ctx)
        count_tokens = lambda text: len(m.tokenizer.encode(text, add_special_tokens=True))  # noqa: E731
        recognized = bootstrap(ctx, conn, col, count_tokens, m.max_seq_length) if first_run else 0

        with conn.cursor() as cur:
            cur.execute(f"SELECT p.payload_id, p.source_table, p.source_id, p.payload_text, p.metadata, {HASH} h, "
                        f"COALESCE(s.part_count, 0) old_parts FROM rag_payloads p LEFT JOIN rag_vector_sync s ON {ON_KEY} "
                        f"WHERE s.source_id IS NULL OR s.content_hash <> {HASH}")
            changed = cur.fetchall()
            cur.execute(f"SELECT s.source_table, s.source_id, s.part_count FROM rag_vector_sync s "
                        f"LEFT JOIN rag_payloads p ON {ON_KEY} WHERE p.source_id IS NULL")
            gone = cur.fetchall()

        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        items, synced, stale = [], [], []
        for row in changed:
            parts = payload_items([row], count_tokens, m.max_seq_length, stamp)
            items += parts
            synced.append((row["source_table"], row["source_id"], row["h"], len(parts), now(), ctx["run_id"]))
            stale += part_ids(row["source_table"], row["source_id"], row["old_parts"])[len(parts):]   # payload got shorter
        for row in gone:
            stale += part_ids(row["source_table"], row["source_id"], row["part_count"])

        # Vector store first, bookkeeping second: a crash in between only repeats this (idempotent) work.
        if items:
            upsert(col, [it["id"] for it in items], [it["text"] for it in items], [it["metadata"] for it in items],
                   embed(ctx, [it["text"] for it in items]))
        delete(col, stale)
        with conn.cursor() as cur:
            if synced:
                cur.executemany("REPLACE INTO rag_vector_sync VALUES (%s,%s,%s,%s,%s,%s)", synced)
            if gone:
                cur.executemany("DELETE FROM rag_vector_sync WHERE source_table=%s AND source_id=%s",
                                [(r["source_table"], r["source_id"]) for r in gone])
            cur.execute("SELECT COALESCE(SUM(part_count), 0) n FROM rag_vector_sync")
            expected = int(cur.fetchone()["n"])
    finally:
        conn.close()

    ctx["vectors_changed"] = ctx.get("vectors_changed", 0) + len(items) + len(stale)
    if col.count() != expected:
        raise RuntimeError(f"gv_erp holds {col.count()} vectors but rag_vector_sync expects {expected}")
    note = f"; {recognized} existing payloads recognized as already embedded" if first_run else ""
    return {"rows_in": len(changed) + len(gone), "rows_out": len(items),
            "message": f"{len(changed)} payloads embedded ({len(items)} vectors), {len(gone)} payloads removed, "
                       f"gv_erp now {expected} vectors{note}"}
