#!/usr/bin/env python3
"""
new_data_batch.py - writes a small, clearly labelled TEST batch into the landing folders,
to demonstrate new data flowing through the pipeline. It never edits existing data files.

The batch (for one real X-7000 unit and one telemetry unit) contains:
    landing/erp/dispatches_<tag>.csv        2 valid service events + 1 for an unknown unit (quarantined)
    landing/erp/warranty_claims_<tag>.csv   1 valid claim + 1 with an unparseable date (quarantined)
    landing/telemetry/telemetry_<tag>.jsonl 3 valid readings + 1 with no equipment_id (quarantined)
    landing/documents/<picked PDFs>          new documents chosen from demo/sample_new_data (a menu)

The PDFs are prepared in demo/sample_new_data (see demo/make_demo_pdfs.py). The menu shows each
one, with "already loaded" if the pipeline has processed that exact file before (same SHA-256),
and copies the chosen ones into the landing folder. If no PDF is chosen, a short .txt procedure
document is written instead, so the document branch always has new input.

Usage:  python new_data_batch.py [--unit EQ-7171] [--telemetry-unit SN-X7-0094] [--pdf 2,3 | all | none]
        (without --pdf, the menu asks)
"""
import argparse
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from config import LANDING_DIRS, mariadb  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "demo" / "sample_new_data"


def pdf_catalog():
    """The prepared PDFs, each marked loaded=True if the pipeline already processed this exact file."""
    path = SAMPLES / "catalog.json"
    if not path.exists():
        return []
    catalog = [e for e in json.loads(path.read_text()) if (SAMPLES / e["file"]).exists()]
    conn = mariadb()
    try:
        with conn.cursor() as cur:
            for entry in catalog:
                digest = hashlib.sha256((SAMPLES / entry["file"]).read_bytes()).hexdigest()
                cur.execute("SELECT 1 FROM etl_file_manifest WHERE file_path=%s AND sha256=%s "
                            "AND status IN ('processed','rejected')",
                            (str(LANDING_DIRS["document"] / entry["file"]), digest))
                entry["loaded"] = cur.fetchone() is not None
    finally:
        conn.close()
    return catalog


def default_pick(catalog):
    """The first readable PDF the pipeline has not loaded yet."""
    return next((i for i, e in enumerate(catalog, 1) if not e["loaded"] and e["question"]), None)


def parse_pick(text, catalog):
    text = (text or "").strip().lower()
    if text in ("none", "0", "n"):
        return []
    if text == "all":
        return list(catalog)
    picked = []
    for token in text.replace(" ", ",").split(","):
        if token.isdigit() and 1 <= int(token) <= len(catalog) and catalog[int(token) - 1] not in picked:
            picked.append(catalog[int(token) - 1])
    return picked


def choose_pdfs(catalog, pick=None, ask=True):
    """Shows the menu and returns the chosen catalog entries."""
    if not catalog:
        return []
    default = default_pick(catalog)
    print("\nNew PDF documents ready in demo/sample_new_data:")
    for i, entry in enumerate(catalog, 1):
        mark = "  (already loaded: copying it again is skipped)" if entry["loaded"] else ""
        print(f"  {i}. {entry['file']}{mark}\n     {entry['shows']}")
    interactive = pick is None and ask and sys.stdin.isatty()
    hint = f"Enter = {default}" if default else "Enter = none"
    while True:
        if interactive:
            pick = input(f"Which PDFs go into the landing folder? (e.g. 2  or 2,3  or all  or none; {hint}): ")
        if not (pick or "").strip():
            pick = str(default) if default else "none"
        chosen = parse_pick(pick, catalog)
        if chosen or pick.strip().lower() in ("none", "0", "n") or not interactive:
            break
        print(f"  '{pick}' is not on the list; type numbers from 1 to {len(catalog)}, all, or none")
    print("Chosen: " + (", ".join(e["file"] for e in chosen) or "none"))
    return chosen


def main(argv=None, ask=True):
    """Writes the batch. Returns {"files": [...], "pdfs": [chosen catalog entries]} for the demo."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", default="EQ-7171")
    ap.add_argument("--telemetry-unit", default="SN-X7-0094")
    ap.add_argument("--pdf", help="PDFs to copy: numbers from the menu (2,3), 'all' or 'none'; omit to be asked")
    args = ap.parse_args(argv)

    stamp = datetime.now(timezone.utc)
    tag = stamp.strftime("%Y%m%d%H%M%S")
    n = stamp.strftime("%H%M%S")                       # keeps IDs unique between batches
    conn = mariadb()
    with conn.cursor() as cur:
        cur.execute("SELECT customer_id, model FROM equipment_units WHERE equipment_id=%s", (args.unit,))
        unit = cur.fetchone()
        cur.execute("SELECT part_id, part_name FROM parts_inventory ORDER BY part_id LIMIT 1")
        part = cur.fetchone()
    conn.close()
    if not unit:
        raise SystemExit(f"{args.unit} is not in equipment_units")
    for folder in LANDING_DIRS.values():
        folder.mkdir(parents=True, exist_ok=True)

    day = (stamp - timedelta(days=1)).strftime("%Y-%m-%d")
    d1, d2, bad_d = f"DISP-T{n}1", f"DISP-T{n}2", f"DISP-T{n}9"
    dispatches = LANDING_DIRS["erp"] / f"dispatches_{tag}.csv"
    with dispatches.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["dispatch_id", "equipment_id", "customer_id", "dispatch_date", "technician", "service_type",
                    "hours_spent", "labor_cost", "resolution_summary", "status"])
        w.writerow([d1, args.unit, unit["customer_id"], day, "Test Batch Technician", "Diagnostic", "2.5", "300.00",
                    "TEST BATCH: Inspected pre-charge circuit after ERR_PRE_003 alarm. Replaced resistor RES-PR-50.", "Completed"])
        w.writerow([d2, args.unit, unit["customer_id"], day, "Test Batch Technician", "Corrective Maintenance", "1.5",
                    "180.00", "TEST BATCH: Verified inverter bay INV-01 contactor torque after inspection.", "Completed"])
        w.writerow([bad_d, "EQ-0000", unit["customer_id"], day, "Test Batch Technician", "Diagnostic", "1.0", "100.00",
                    "TEST BATCH: Dispatch for a unit that does not exist (should be quarantined).", "Pending"])

    claims = LANDING_DIRS["erp"] / f"warranty_claims_{tag}.csv"
    with claims.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["claim_id", "equipment_id", "dispatch_id", "part_id", "claim_date", "claim_amount",
                    "approved_amount", "status", "denial_reason", "claim_notes"])
        w.writerow([f"CLM-T{n}1", args.unit, d1, part["part_id"], day, "845.00", "", "Pending", "",
                    "TEST BATCH: Claim for pre-charge resistor replacement."])
        w.writerow([f"CLM-T{n}9", args.unit, d1, part["part_id"], "not-a-date", "100.00", "", "Pending", "",
                    "TEST BATCH: Claim with an invalid date (should be quarantined)."])

    telemetry = LANDING_DIRS["telemetry"] / f"telemetry_{tag}.jsonl"
    base = stamp - timedelta(days=1)
    readings = [
        ("RAMP_UP", None, "Info", 980, 1500, 38.2, [], "TEST BATCH: Scheduled ramp initiated."),
        ("FAULT", "ERR_PRE_003", "High", 1750, 0, 39.1, ["RES-PR-50"], "TEST BATCH: Pre-charge resistor fault detected."),
        ("STANDBY", None, "Info", 980, 0, 36.0, [], "TEST BATCH: Unit returned to standby after resistor replacement."),
    ]
    with telemetry.open("w") as fh:
        for i, (status, fault, sev, v, a, t, parts, note) in enumerate(readings, start=1):
            fh.write(json.dumps({"log_id": f"TLM-T{n}{i}", "timestamp": (base + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                                 "equipment_id": args.telemetry_unit, "model": "Gigavolt Megapack X-7000", "status": status,
                                 "fault_code": fault, "severity": sev,
                                 "telemetry": {"voltage_v": v, "current_a": a, "temperature_c": t, "soc_percent": 52.0,
                                               "voltage_delta_mv": 14}, "flagged_components": parts, "notes": note}) + "\n")
        fh.write(json.dumps({"log_id": f"TLM-T{n}9", "timestamp": base.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                             "model": "Gigavolt Megapack X-7000", "status": "FAULT",
                             "notes": "TEST BATCH: reading with no equipment_id (should be quarantined)."}) + "\n")

    written = [dispatches, claims, telemetry]
    pdfs = choose_pdfs(pdf_catalog(), args.pdf, ask)
    for entry in pdfs:
        target = LANDING_DIRS["document"] / entry["file"]
        shutil.copy2(SAMPLES / entry["file"], target)
        written.append(target)
    if not pdfs:
        written.append(write_txt_document(n))

    for path in written:
        print(f"wrote {path}")
    print(f"\nNew IDs to ask about: {d1}, {d2}, CLM-T{n}1, telemetry TLM-T{n}1..3 on {args.telemetry_unit}")
    for entry in pdfs:
        if entry["question"]:
            print(f"Ask about {entry['file'].split('_')[0]}: {entry['question']}")
    return {"files": written, "pdfs": pdfs, "dispatches_csv": dispatches, "claims_csv": claims,
            "dispatch_ids": [d1, d2, bad_d], "claim_ids": [f"CLM-T{n}1", f"CLM-T{n}9"]}


def write_txt_document(n):
    doc = LANDING_DIRS["document"] / f"GV-SOP-TEST-{n}_Precharge_Resistor_Inspection.txt"
    doc.write_text(
        "Standard Operating Procedure: Pre-Charge Resistor Inspection (TEST BATCH)\n\n"
        "Purpose\nThis test procedure describes how technicians inspect the pre-charge resistor RES-PR-50 "
        "on the Megapack X-7000 after an ERR_PRE_003 alarm.\n\n"
        "Steps\n1. Isolate the DC bus and confirm zero energy with an intrinsically safe meter.\n"
        "2. Measure the resistance of RES-PR-50; replace it if the reading is outside 47 to 53 ohms.\n"
        "3. Inspect the wirewound terminals for heat discoloration and re-torque them to 4.5 N m.\n"
        "4. Re-energize, run a scheduled ramp, and confirm no ERR_PRE_003 alarm within 10 minutes.\n")
    return doc


if __name__ == "__main__":
    main()
