"""
tasks_telemetry.py - incremental telemetry loading: validate each reading, then upsert into MongoDB.

The Milestone 5 loader's parsing rules are reused (required fields, real Date timestamps,
model_key, source file and line). Two things differ: a bad line goes to the quarantine with its
reason instead of only being printed, and readings are upserted by log_id, so an existing
collection is extended rather than dropped and reloaded. Re-running a file changes nothing.
"""
from config import mongo_collection

LIMITS = {"temperature_c": (-60, 250), "soc_percent": (0, 100), "voltage_v": (0, 5000)}


def out_of_range(doc):
    """Physically impossible sensor values are data errors, not readings."""
    values = doc.get("telemetry") if isinstance(doc.get("telemetry"), dict) else {}
    for field, (low, high) in LIMITS.items():
        value = values.get(field)
        if isinstance(value, (int, float)) and not low <= value <= high:
            return f"{field} {value} outside {low}..{high}"
    return None


def load(ctx):
    files = [f for f in ctx["files"] if f["source"] == "telemetry"]
    if not files:
        return {"status": "skipped", "message": "no new telemetry files"}
    from pymongo import ReplaceOne

    import load_telemetry as loader

    col = mongo_collection()
    total_in = upserted = modified = rejected = 0
    for f in files:
        docs, errors = loader.read_documents(f["path"])
        good = []
        for doc in docs:
            problem = out_of_range(doc)
            if problem:
                errors.append(f"line {doc['source']['line']}: {problem}")
            else:
                good.append(doc)
        for err in errors:                              # e.g. "line 7: missing equipment_id"
            line, _, reason = err.partition(": ")
            ctx["state"].quarantine(ctx["run_id"], "telemetry", f["path"], line, reason, {"error": err})
        total_in += len(good) + len(errors)
        rejected += len(errors)
        if good:
            result = col.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in good], ordered=False)
            upserted += result.upserted_count
            modified += result.modified_count
        ctx.setdefault("rows_by_file", {})[str(f["path"])] = len(good)
    for name, keys in loader.INDEXES:                   # idempotent: keeps the indexes in place on every run
        col.create_index(keys, name=name)
    ctx["telemetry_changed"] = upserted + modified
    ctx["telemetry_rejected"] = rejected
    return {"rows_in": total_in, "rows_out": upserted + modified,
            "message": f"{upserted} new, {modified} updated, {total_in - rejected - upserted - modified} unchanged, "
                       f"{rejected} quarantined"}
