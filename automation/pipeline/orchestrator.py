"""
orchestrator.py - a small DAG runner for the Gigavolt data pipeline.

Each task names the tasks it depends on. Tasks run in dependency (topological) order.
  * A task whose dependency failed is marked "blocked" and skipped, so bad data never
    moves downstream.
  * A task with trigger="all_done" runs even when a dependency failed. The integrity check
    and the cache refresh use it, so the branches that did succeed are still verified and
    still become visible to the RAG pipeline.
  * Every task gets retries with exponential backoff, timing, row counts and a log entry,
    and every task result is recorded in MariaDB (etl_task_runs).

A task function receives the shared run context and returns a dict:
    {"status": "success" | "skipped", "rows_in": int, "rows_out": int, "message": str}
Raising an exception means the attempt failed.
"""
import fcntl
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from config import LOCK_FILE, STATE, get_logger, now

FAILED = ("failed", "blocked")


@dataclass
class Task:
    name: str
    func: Callable[[dict], dict]
    deps: List[str] = field(default_factory=list)
    retries: int = 2
    retry_delay: float = 2.0
    trigger: str = "all_success"        # or "all_done"


class Pipeline:
    def __init__(self, tasks: List[Task]):
        self.tasks = {t.name: t for t in tasks}
        self.order = self._topological_order()

    def _topological_order(self):
        """Depth-first ordering. Rejects unknown dependencies and cycles, so the graph is a real DAG."""
        order, visiting, done = [], set(), set()

        def visit(name):
            if name in done:
                return
            if name in visiting:
                raise ValueError(f"dependency cycle at {name}")
            visiting.add(name)
            for dep in self.tasks[name].deps:
                if dep not in self.tasks:
                    raise ValueError(f"{name} depends on unknown task {dep}")
                visit(dep)
            visiting.discard(name)
            done.add(name)
            order.append(name)
        for name in self.tasks:
            visit(name)
        return order

    def run(self, ctx: Dict, state, run_id: str):
        log = get_logger()
        results = {}
        ctx["task_results"] = results
        for name in self.order:
            task = self.tasks[name]
            failed_deps = [d for d in task.deps if results[d]["status"] in FAILED]
            started = now()
            if failed_deps and task.trigger != "all_done":
                results[name] = {"status": "blocked", "message": f"blocked by {', '.join(failed_deps)}",
                                 "duration_ms": 0, "attempts": 0}
                log.warning(f"[{name}] blocked by {', '.join(failed_deps)}")
            else:
                results[name] = self._run_task(task, ctx)
            r = results[name]
            try:
                state.record_task(run_id, name, r["status"], started, r.get("duration_ms", 0), r.get("attempts", 0),
                                  r.get("rows_in"), r.get("rows_out"), r.get("message"))
            except Exception as exc:  # noqa: BLE001 - bookkeeping must not stop the run
                log.error(f"[{name}] could not record the task result: {exc}")
        return results

    def _run_task(self, task: Task, ctx: Dict):
        log = get_logger()
        start = time.perf_counter()
        delay = task.retry_delay
        for attempt in range(1, task.retries + 2):
            try:
                result = task.func(ctx) or {}
                result.setdefault("status", "success")
                result["attempts"] = attempt
                result["duration_ms"] = (time.perf_counter() - start) * 1000
                log.info(f"[{task.name}] {result['status']} in {result['duration_ms']:.0f} ms"
                         + (f" - {result['message']}" if result.get("message") else ""),
                         extra={"extra": {"task": task.name, **{k: v for k, v in result.items() if k != 'message'}}})
                return result
            except Exception as exc:  # noqa: BLE001 - recorded and retried
                message = f"{type(exc).__name__}: {exc}"
                if attempt <= task.retries:
                    log.warning(f"[{task.name}] attempt {attempt} failed ({message[:150]}); retrying in {delay:.0f}s")
                    time.sleep(delay)
                    delay *= 2
                    continue
                log.error(f"[{task.name}] failed after {attempt} attempts: {message[:300]}",
                          extra={"extra": {"task": task.name, "status": "failed",
                                           "traceback": traceback.format_exc()[-1500:]}})
                return {"status": "failed", "message": message[:1000], "attempts": attempt,
                        "duration_ms": (time.perf_counter() - start) * 1000}


class RunLock:
    """Prevents two pipeline runs (for example a timer run and a manual run) from overlapping."""

    def __enter__(self):
        STATE.mkdir(parents=True, exist_ok=True)
        self.handle = open(LOCK_FILE, "w")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another pipeline run is in progress; exiting.")
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()
