"""
m6_rag.py - the optimized RAG pipeline. It extends the Milestone 5 classes instead of replacing
them, so the benchmark can run the original ("baseline") and this version ("optimized") side by side.

Performance
  1. MariaDB connection pool   connections are kept open and reused (Milestone 5 opened one per query)
  2. Index-friendly SQL        a claim is found through warranty_claims' primary key instead of a
                               LIKE scan over every payload; unit lookups use the new indexes
                               (sql/10_index_tuning.sql)
  3. Aggregate cache           per-model fleet and telemetry summaries are cached per data version
  4. Query-embedding cache     a repeated question is not embedded again
  5. Answer cache              a repeated question on unchanged data skips retrieval and the LLM;
                               the pipeline's data version is part of the key, so new data clears it
  6. Smaller context           10 snippets / 7,000 characters by default (14 / 9,000 only for unit
                               histories), so the LLM reads less text
Retrieval fidelity
  7. Time windows              "in 2021", "September 2026", "on 2024-09-28" filter SQL and MongoDB
                               by date, so temporal questions get the records of that period
  8. Fresh stores              when the pipeline publishes a new data version, the vector
                               collections are reopened, so new data is visible without a restart
Provenance
  9. Better statement splitting  "Step 1." is no longer counted as a sentence
 10. One regeneration            if the verifier flags a statement, the LLM rewrites the answer once
                                 with the problems listed
 11. Strict mode                 a statement that still cannot be traced is removed before display,
                                 and reported, so every displayed fact traces to a cited source
 12. Audit trail                 every answer is appended to logs/rag_audit.jsonl with each
                                 statement, its verdict, and each source's database, record ID,
                                 document, chunk, timestamp and content hash
"""
import copy
import hashlib
import json
import os
import queue
import re
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC = Path(os.environ.get("GIGAVOLT_SRC", "/opt/gigavolt/src"))
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from hybrid_retrieval import (DocumentRetriever, HybridRetriever, Snippet, SQLRetriever,  # noqa: E402
                                 VectorRetriever, assemble_context)
from rag_pipeline import (CITATION_RE, SENTENCE_RE, RagPipeline, build_prompt,  # noqa: E402
                             extractive_verification, verify_answer)

try:
    from config import ROOT, read_data_version  # noqa: E402
except ImportError:                          # running outside the pipeline layout
    ROOT = Path("/opt/gigavolt")

    def read_data_version():
        return "initial"

AUDIT_LOG = Path(os.environ.get("RAG_AUDIT_LOG", ROOT / "logs" / "rag_audit.jsonl"))
STEP_RE = re.compile(r"\b(Step|Stage|Phase|No\.?)\s+(\d+)\.(?=\s)")
BULLET_RE = re.compile(r"^(\s*(?:[-*•]|\d+[.)])\s+)?(.*)$")
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
MONTH_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(20\d{2})\b", re.I)
DAY_RE = re.compile(r"(?<![-\w])(20\d{2})-(\d{2})-(\d{2})(?![-\w])")
YEAR_RE = re.compile(r"(?<![-\w])(20\d{2})(?![-\w])")


def time_window(question):
    """(start, end, label) for a date, month or year named in the question, else None. End is exclusive."""
    try:
        m = DAY_RE.search(question)
        if m:
            start = datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
            return start, start + timedelta(days=1), m[0]
        m = MONTH_RE.search(question)
        if m:
            month, year = MONTHS.index(m[1].lower()) + 1, int(m[2])
            start = datetime(year, month, 1, tzinfo=timezone.utc)
            end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=timezone.utc)
            return start, end, f"{m[1].capitalize()} {year}"
        m = YEAR_RE.search(question)
        if m:
            year = int(m[1])
            return datetime(year, 1, 1, tzinfo=timezone.utc), datetime(year + 1, 1, 1, tzinfo=timezone.utc), str(year)
    except ValueError:
        pass
    return None


class LRUCache:
    def __init__(self, size=256, ttl_seconds=3600):
        self.size, self.ttl, self.data, self.lock = size, ttl_seconds, OrderedDict(), threading.Lock()
        self.hits = self.misses = 0

    def get(self, key):
        with self.lock:
            item = self.data.get(key)
            if item and time.time() - item[0] < self.ttl:
                self.data.move_to_end(key)
                self.hits += 1
                return item[1]
            self.misses += 1
            return None

    def put(self, key, value):
        with self.lock:
            self.data[key] = (time.time(), value)
            self.data.move_to_end(key)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


def cached_snippets(cache, key, build):
    """Snippets are copied on the way out: assembling a context writes a tag onto each one."""
    found = cache.get(key)
    if found is None:
        found = build()
        cache.put(key, found)
    return [copy.copy(s) for s in found]


class PooledSQLRetriever(SQLRetriever):
    """The Milestone 5 queries with pooled connections, date windows and an aggregate cache."""

    def __init__(self, pool_size=4):
        super().__init__()
        self._idle = queue.LifoQueue()
        self._pool_size = pool_size
        self.aggregates = LRUCache(size=64, ttl_seconds=600)

    def _connection(self):
        try:
            conn = self._idle.get_nowait()
            conn.ping(reconnect=True)            # survives a database restart
            return conn
        except queue.Empty:
            return self._pymysql.connect(**self._settings)

    def _rows(self, sql, params=()):
        conn = self._connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        except Exception:
            conn.close()
            raise
        if self._idle.qsize() < self._pool_size:
            self._idle.put(conn)
        else:
            conn.close()
        return rows

    def record(self, record_id):
        """A dispatch is its own payload. A claim is either its own payload or a line inside its
        dispatch's payload; the join finds that dispatch by primary key (no text scan)."""
        rows = self._rows(
            "SELECT source_id, payload_text, event_date FROM rag_payloads WHERE source_table IN ('service_logs','warranty_claims') AND source_id=%s "
            "UNION SELECT p.source_id, p.payload_text, p.event_date FROM warranty_claims wc JOIN rag_payloads p "
            "ON p.source_table='service_logs' AND p.source_id=wc.dispatch_id AND p.equipment_id=wc.equipment_id "
            "WHERE wc.claim_id=%s", (record_id, record_id))
        if rows:
            return [self._payload_snippet(row) for row in rows]
        return [Snippet("mariadb", "rag_payloads", f"lookup:{record_id}",
                        f"No ERP service or warranty record exists for {record_id}.")]

    def unit(self, identifier, max_events=12, window=None):
        out = super().unit(identifier, max_events)
        if not window or out[0].record_id.startswith("lookup:"):
            return out
        start, end, label = window
        events = self._rows("SELECT source_id, payload_text, event_date FROM rag_payloads WHERE equipment_id=%s "
                            "AND event_date >= %s AND event_date < %s ORDER BY event_date DESC LIMIT %s",
                            (out[0].record_id, start.date(), end.date(), max_events))
        if not events:
            return out[:1] + [Snippet("mariadb", "rag_payloads", f"lookup:{out[0].record_id}:{label}",
                                      f"No service or warranty record dated in {label} exists for unit {out[0].record_id}.")]
        return out[:1] + [self._payload_snippet(row) for row in events]

    def model_summary(self, model):
        return cached_snippets(self.aggregates, (model, read_data_version()), lambda: super(PooledSQLRetriever, self).model_summary(model))

    def retrieve(self, plan):
        window = time_window(plan.question)
        out = []
        for identifier in plan.equipment_ids + plan.serials:
            out += self.unit(identifier, window=window)
        for record_id in plan.dispatch_ids + plan.claim_ids:
            out += self.record(record_id)
        if plan.wants_supplier:
            out += self.suppliers(plan.question)
        if plan.wants_failure or plan.wants_thermal or plan.wants_history:
            for model in plan.models:
                out += self.model_summary(model)
        return out


class CachedVectorRetriever(VectorRetriever):
    def __init__(self):
        super().__init__()
        self.vector_cache = LRUCache(size=512, ttl_seconds=24 * 3600)

    def encode(self, question):
        key = " ".join(question.lower().split())
        vector = self.vector_cache.get(key)
        if vector is None:
            vector = super().encode(question)
            self.vector_cache.put(key, vector)
        return vector

    def reopen(self):
        """Another process (the data pipeline) wrote to ChromaDB: open the collections again."""
        import chromadb
        try:
            from chromadb.api.shared_system_client import SharedSystemClient
            SharedSystemClient.clear_system_cache()
        except Exception:  # noqa: BLE001 - older or newer Chroma: a fresh client is still created below
            pass
        client = chromadb.PersistentClient(path=os.environ.get("CHROMA_PATH", "/opt/gigavolt/chroma_db"))
        self.manuals = client.get_collection("gv_manuals", embedding_function=None)
        self.erp = client.get_collection("gv_erp", embedding_function=None)


class WindowedDocumentRetriever(DocumentRetriever):
    """Adds date windows for a named unit, and caches the per-model telemetry summaries."""

    def __init__(self):
        super().__init__()
        self.aggregates = LRUCache(size=64, ttl_seconds=600)

    def unit(self, equipment_id, window=None):
        if not window:
            return super().unit(equipment_id)
        start, end, label = window
        match = {"equipment_id": equipment_id, "timestamp": {"$gte": start, "$lt": end}}
        total = self.col.count_documents(match)
        if not total:
            return [Snippet("mongodb", "bms_telemetry", f"lookup:{equipment_id}:{label}",
                            f"No telemetry reading dated in {label} exists for unit {equipment_id}.")]
        summary = self._summary(match, f"aggregate:unit:{equipment_id}:{label}",
                                f"Telemetry fault summary for unit {equipment_id} in {label} ({total} readings in total)")
        if not summary:
            summary = [Snippet("mongodb", "bms_telemetry", f"aggregate:unit:{equipment_id}:{label}",
                               f"Unit {equipment_id} has {total} telemetry readings in {label} and none has a fault code.")]
        # In time order, faults first when there are more readings than fit
        docs = list(self.col.find({**match, "fault_code": {"$ne": None}}).sort("timestamp", 1).limit(8))
        if len(docs) < 8:
            docs += list(self.col.find({**match, "fault_code": None}).sort("timestamp", 1).limit(8 - len(docs)))
        docs.sort(key=lambda d: d["timestamp"])
        return summary + [self._reading(doc) for doc in docs]

    def model(self, model, thermal, unit_context=None):
        return cached_snippets(self.aggregates, (model, thermal, unit_context, read_data_version()),
                               lambda: super(WindowedDocumentRetriever, self).model(model, thermal, unit_context))

    def retrieve(self, plan, unit_models):
        window = time_window(plan.question)
        if not (window and plan.serials):
            return super().retrieve(plan, unit_models)
        out = []
        for serial in plan.serials:
            out += self.unit(serial, window)
        for code in plan.fault_codes:
            out += self.fault(code)
        return out


class OptimizedHybridRetriever(HybridRetriever):
    def __init__(self):                       # replaces the stores with pooled, cached and windowed versions
        self.sql = PooledSQLRetriever()
        self.vector = CachedVectorRetriever()
        self.document = WindowedDocumentRetriever()
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="retriever")


def normalize(question):
    return " ".join(re.sub(r"[^\w\s-]", " ", question.lower()).split())


def clean(answer):
    return STEP_RE.sub(r"\1 \2:", answer)


def remove_statements(answer, problems):
    """Drops the flagged sentences and keeps everything else, including the bullet layout."""
    flagged = {p["statement"] for p in problems}
    lines = []
    for line in answer.splitlines():
        prefix, body = BULLET_RE.match(line.replace("**", "")).groups()
        kept = [part for part in SENTENCE_RE.split(body.strip()) if part.strip() and part.strip() not in flagged]
        if kept:
            lines.append((prefix or "") + " ".join(kept))
    return "\n".join(lines)


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def assemble(result, max_snippets, max_chars):
    """Milestone 5 assembly, plus: a named unit's records may not fill the whole context when other
    stores also returned evidence (a multi-hop question needs both)."""
    others = sum(1 for name, items in result.snippets.items() if name != "sql" and items)
    if result.plan.has_exact_entity and others and len(result.snippets.get("sql", [])) > max_snippets - 3:
        result.snippets["sql"] = result.snippets["sql"][:max_snippets - 3]
    return assemble_context(result, max_snippets=max_snippets, max_chars=max_chars)


class OptimizedRagPipeline(RagPipeline):
    def __init__(self, max_snippets=10, max_chars=7000, answer_cache=True, regenerate=True, strict=True, backend=None, retriever=None):
        from rag_pipeline import make_backend
        self.retriever = retriever or OptimizedHybridRetriever()
        self.backend = backend or make_backend()
        self.max_snippets, self.max_chars = max_snippets, max_chars
        self.cache = LRUCache() if answer_cache else None
        self.regenerate, self.strict = regenerate, strict
        self.data_version = read_data_version()

    def _stay_fresh(self):
        version = read_data_version()
        if version != self.data_version:
            self.retriever.vector.reopen()
            self.data_version = version
        return version

    def ask(self, question):
        started = time.perf_counter()
        version = self._stay_fresh()
        key = (normalize(question), version)
        if self.cache:
            cached = self.cache.get(key)
            if cached:
                record = copy.deepcopy(cached)
                record["cache_hit"] = True
                lookup = (time.perf_counter() - started) * 1000     # every other stage was skipped
                record["timings_ms"] = {**{stage: 0.0 for stage in cached["timings_ms"]}, "cache_lookup": lookup,
                                        "total": lookup}
                return record

        result = self.retriever.retrieve(question)
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        timings = dict(result.timings_ms)
        start = time.perf_counter()
        history = result.plan.has_exact_entity and result.plan.wants_history
        snippets = assemble(result, 14 if history else self.max_snippets, 9000 if history else self.max_chars)
        prompt = build_prompt(snippets, question)
        timings["assemble"] = (time.perf_counter() - start) * 1000

        answer, llm_error = self._generate(prompt, snippets, timings)
        generate_ms, wait_ms = timings["generate"], timings.get("rate_limit_wait", 0)
        regenerated, removed, llm_calls = False, [], 1
        start = time.perf_counter()
        if llm_error:                       # the fallback answer is copied from the evidence line by line
            check = extractive_verification(snippets)
        else:
            answer = clean(answer)
            check = verify_answer(answer, snippets)
        verify_ms = (time.perf_counter() - start) * 1000

        problems = [s for s in check["statements"] if s["verdict"] == "problem"]
        if problems and not llm_error and self.regenerate:
            feedback = "\n".join(f"- {'; '.join(p['problems'])}: {p['statement']}" for p in problems)
            retry_prompt = (prompt + "\n\nYour previous answer had statements that could not be traced to the evidence:\n"
                            + feedback + "\nRewrite the whole answer. End every factual sentence with its [S#] tag and "
                            "copy numbers, IDs and dates exactly from the cited snippet.")
            answer2, error2 = self._generate(retry_prompt, snippets, timings)
            generate_ms += timings["generate"]
            wait_ms += timings.get("rate_limit_wait", 0)
            llm_calls += 1
            if not error2:
                answer2 = clean(answer2)
                check2 = verify_answer(answer2, snippets)
                regenerated = True
                if check2["supported"] / max(check2["factual"], 1) >= check["supported"] / max(check["factual"], 1):
                    answer, check = answer2, check2
                    problems = [s for s in check["statements"] if s["verdict"] == "problem"]
        if problems and not llm_error and self.strict:
            removed = [p["statement"] for p in problems]
            answer = remove_statements(answer, problems)
            if not re.search(r"[A-Za-z]", CITATION_RE.sub("", answer)):
                answer = "The available records do not show a verifiable answer to this question."
            check = verify_answer(answer, snippets)
        timings.update(generate=generate_ms, rate_limit_wait=wait_ms, verify=verify_ms)
        timings["total"] = (time.perf_counter() - started) * 1000

        check["omitted_records"] = []
        if history and not llm_error:
            check["omitted_records"] = [s.record_id for s in snippets if s.source == "rag_payloads"
                                        and s.record_id not in answer]
        cited = {tag for s in check["statements"] for tag in s["cites"]}
        record = {"question": question, "answer": answer, "backend": self.backend.name, "llm_error": llm_error,
                  "store_errors": result.errors, "routing": result.plan.reasons, "timings_ms": timings,
                  "sources": [{**s.citation(), "cited": s.tag in cited, "retrieved_at": retrieved_at,
                               "text_sha": text_hash(s.text)} for s in snippets],
                  "verification": check, "regenerated": regenerated, "llm_calls": llm_calls,
                  "removed_statements": removed, "cache_hit": False, "data_version": version}
        self._audit(record)
        if self.cache and not llm_error and not result.errors:
            self.cache.put(key, record)
        return record

    @staticmethod
    def _audit(record):
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"asked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                         **record}, default=str) + "\n")
        except OSError as exc:
            print(f"WARNING: could not write {AUDIT_LOG}: {exc}")
