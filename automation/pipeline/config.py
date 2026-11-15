"""config.py - paths, connections and retry helpers shared by every pipeline task."""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("GIGAVOLT_ROOT", "/opt/gigavolt"))
SRC = Path(os.environ.get("GIGAVOLT_SRC", ROOT / "src"))      # Phase 4 and 5 modules
LANDING = ROOT / "landing"                                     # new data is dropped here
LANDING_DIRS = {"erp": LANDING / "erp", "telemetry": LANDING / "telemetry", "document": LANDING / "documents"}
MANUALS = ROOT / "manuals"
STATE = ROOT / "state"
DATA_VERSION = STATE / "data_version"                          # bumped when data changes; clears answer caches
LOCK_FILE = STATE / "pipeline.lock"
LOG_FILE = ROOT / "logs" / "pipeline.jsonl"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {"ts": now().isoformat(timespec="milliseconds"), "level": record.levelname, "msg": record.getMessage()}
        entry.update(getattr(record, "extra", {}))
        return json.dumps(entry, default=str)


def get_logger():
    log = logging.getLogger("gigavolt.pipeline")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
    log.addHandler(console)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(JsonFormatter())
        log.addHandler(file_handler)
    except OSError:
        pass
    return log


def with_retry(func, attempts=5, first_delay=1.0, what="operation"):
    """Retry with exponential backoff, so a database restart or network blip is survived."""
    delay = first_delay
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - every transient error is retried the same way
            if attempt == attempts:
                raise
            get_logger().warning(f"{what} failed ({type(exc).__name__}: {str(exc)[:120]}); "
                                 f"retry {attempt}/{attempts - 1} in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2


def mariadb(autocommit=True, local_infile=False):
    import pymysql

    def connect():
        return pymysql.connect(host=os.environ.get("MARIADB_HOST", "127.0.0.1"),
                               port=int(os.environ.get("MARIADB_PORT", 3306)),
                               user=os.environ["MARIADB_USER"], password=os.environ["MARIADB_PASSWORD"],
                               database=os.environ.get("MARIADB_DB", "gigavolt_erp"), charset="utf8mb4",
                               autocommit=autocommit, local_infile=local_infile, connect_timeout=5,
                               cursorclass=pymysql.cursors.DictCursor)
    return with_retry(connect, what="MariaDB connection")


def mongo_collection():
    from pymongo import MongoClient

    def connect():
        client = MongoClient(os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017"), serverSelectionTimeoutMS=4000)
        client.admin.command("ping")
        return client[os.environ.get("MONGO_DB", "gigavolt_iot")]["bms_telemetry"]
    return with_retry(connect, what="MongoDB connection")


def chroma_client():
    import chromadb
    return chromadb.PersistentClient(path=os.environ.get("CHROMA_PATH", str(ROOT / "chroma_db")))


def bump_data_version(run_id):
    STATE.mkdir(parents=True, exist_ok=True)
    DATA_VERSION.write_text(f"{run_id}\n")


def read_data_version():
    try:
        return DATA_VERSION.read_text().strip()
    except OSError:
        return "initial"
