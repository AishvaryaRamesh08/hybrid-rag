"""state.py - pipeline bookkeeping in MariaDB: runs, task results, file manifest, quarantine, flags."""
import hashlib
import json

from config import LANDING_DIRS, get_logger, mariadb, now, with_retry

EXTENSIONS = {"erp": (".csv",), "telemetry": (".json", ".jsonl"), "document": (".pdf", ".txt")}
MAX_FILE_ATTEMPTS = 3      # a file that keeps failing is set aside instead of being retried forever


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class State:
    def __init__(self):
        self.conn = mariadb()

    def _exec(self, sql, params=()):
        def run():
            self.conn.ping(reconnect=True)      # reconnects after a database restart
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        return with_retry(run, what="pipeline state query")

    # ---------------------------------------------------------------- runs
    def start_run(self, run_id, trigger):
        self._exec("INSERT INTO etl_runs (run_id, started_at, status, trigger_type) VALUES (%s,%s,'running',%s)",
                   (run_id, now(), trigger))

    def finish_run(self, run_id, status, summary):
        self._exec("UPDATE etl_runs SET finished_at=%s, status=%s, summary=%s WHERE run_id=%s",
                   (now(), status, json.dumps(summary, default=str), run_id))

    def record_task(self, run_id, task, status, started, duration_ms, attempts, rows_in, rows_out, message):
        self._exec("REPLACE INTO etl_task_runs VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                   (run_id, task, status, started, int(duration_ms), attempts, rows_in, rows_out, (message or "")[:1000]))

    # ---------------------------------------------------------------- files
    def detect_new_files(self):
        """Every landing file whose content (path + SHA-256) has not been handled yet.

        Handled means processed, rejected (wrong layout) or failed MAX_FILE_ATTEMPTS times.
        A file whose content changes gets a new hash, so it is picked up again."""
        found = []
        for source, folder in LANDING_DIRS.items():
            folder.mkdir(parents=True, exist_ok=True)
            for path in sorted(folder.iterdir()):
                if not path.is_file() or path.suffix.lower() not in EXTENSIONS[source]:
                    continue
                digest = sha256(path)
                seen = self._exec("SELECT status, attempts FROM etl_file_manifest WHERE file_path=%s AND sha256=%s",
                                  (str(path), digest))
                if seen and seen[0]["status"] in ("processed", "rejected"):
                    continue
                if seen and seen[0]["status"] == "failed" and seen[0]["attempts"] >= MAX_FILE_ATTEMPTS:
                    get_logger().warning(f"{path.name} failed {seen[0]['attempts']} times and is no longer retried")
                    continue
                found.append({"path": path, "sha256": digest, "source": source, "size": path.stat().st_size})
        return found

    def register_files(self, files, run_id):
        for f in files:
            self._exec("INSERT INTO etl_file_manifest (file_path, sha256, source_type, size_bytes, first_seen, run_id, "
                       "status, attempts) VALUES (%s,%s,%s,%s,%s,%s,'pending',1) "
                       "ON DUPLICATE KEY UPDATE run_id=VALUES(run_id), status='pending', attempts=attempts+1",
                       (str(f["path"]), f["sha256"], f["source"], f["size"], now(), run_id))

    def mark_file(self, f, status, run_id, rows=None):
        self._exec("UPDATE etl_file_manifest SET status=%s, processed_at=%s, run_id=%s, rows_loaded=%s "
                   "WHERE file_path=%s AND sha256=%s", (status, now(), run_id, rows, str(f["path"]), f["sha256"]))

    # ---------------------------------------------------------------- quarantine
    def quarantine(self, run_id, source, source_file, record_key, reason, raw):
        self._exec("INSERT INTO etl_quarantine (run_id, source_type, source_file, record_key, reason, raw_record) "
                   "VALUES (%s,%s,%s,%s,%s,%s)",
                   (run_id, source, str(source_file) if source_file else None, record_key, reason[:255],
                    json.dumps(raw, default=str)))

    # ---------------------------------------------------------------- durable flags
    def get_flag(self, key, default=None):
        rows = self._exec("SELECT state_value FROM etl_state WHERE state_key=%s", (key,))
        return rows[0]["state_value"] if rows else default

    def set_flag(self, key, value):
        self._exec("REPLACE INTO etl_state (state_key, state_value) VALUES (%s,%s)", (key, str(value)))
