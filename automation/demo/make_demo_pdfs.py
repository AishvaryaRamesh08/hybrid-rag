#!/usr/bin/env python3
"""
make_demo_pdfs.py - builds the NEW documents used in the demo video, in demo/sample_new_data/.

Move them into the landing folder ONE AT A TIME during the demo; each one shows something different.

  #  File                                                         Shows
  1  GV-ECO-2026-077_Change_Order_Precharge_Resistor_Upgrade.pdf  new PDF -> chunked + embedded (text + table)
  2  GV-INC-2026-131_Field_Incident_Coolant_Pump_Bearing_Failure.pdf  second new PDF, other model (G-3500)
  3  GV-SOP-INSP-715_SOP_Thermal_Imaging_Inspection.pdf           third new PDF, C-1200, a 2-page table
  4  GV-TSB-2026-014_Technical_Service_Bulletin_Firmware_7.5.0.pdf a new document TYPE (TSB) for all models
  5  GV-SOP-SCAN-999_Scanned_Inspection_Checklist.pdf             error handling: image-only "scan",
                                                                  no text -> file quarantined, never retried

Every fact in 1-4 (IDs, part numbers, values) exists in NO other document, so an answer that
quotes them can only come from the new file. Each file's demo question is stored with it in
sample_new_data/catalog.json.

You do not copy these by hand: the demo (part 1) runs ops/new_data_batch.py, which shows this
list and copies the PDFs you pick into the landing folder, next to the CSV and telemetry batch.

Needs reportlab (pip install reportlab), only to rebuild the PDFs; the built files are shipped.
"""
import json
from pathlib import Path

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

rl_config.invariant = 1        # same bytes on every rebuild, so the SHA-256 fingerprint never changes
OUT = Path(__file__).resolve().parent / "sample_new_data"

styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=16, leading=20, alignment=0)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=10)
BODY = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=14)

DOCS = [
    {
        "file": "GV-ECO-2026-077_Change_Order_Precharge_Resistor_Upgrade.pdf",
        "shows": "Megapack X-7000 change order: new resistor part, affected serials (text + table)",
        "title": "Engineering Change Order: Megapack X-7000 Pre-Charge Resistor Upgrade",
        "header": ["ECO Tracking Identifier: ECO-2026-077",
                   "Target Platform: Gigavolt Megapack X-7000 (Model: X-7000)",
                   "Effective Manufacturing Date: November 1, 2026",
                   "Impacted Subsystem: DC Bus Pre-Charge Circuit (Part Number: RES-PR-50)",
                   "Originating Engineer: Priya Natarajan, Principal Power Electronics Engineer"],
        "sections": [
            ("Justification &amp; Root Cause", [
                "Field telemetry from utility-scale X-7000 installations recorded repeated ERR_PRE_003 "
                "(pre-charge timeout) alarms during cold-morning ramp-ups. Teardown of 9 returned units showed "
                "that the 50-ohm wirewound pre-charge resistor (RES-PR-50) drifted above 56 ohms after roughly "
                "1,800 charge cycles, which extends the pre-charge time beyond the 4.0 second BMS limit. In 3 "
                "documented field instances the resistor terminals showed heat discoloration and loosened lugs."]),
            ("Engineering Retrofit Details", [
                "1. Component Replacement: Replace RES-PR-50 with the aluminium-housed, 75-ohm, 300 W "
                "pre-charge resistor (Part Number: RES-PR-75) on every affected unit.",
                "2. Terminal Hardware: Fit the new resistor with M6 ring lugs and torque the terminals to 6.0 N m "
                "(the previous specification was 4.5 N m).",
                "3. Firmware Parameter: Raise the BMS pre-charge timeout from 4.0 s to 5.5 s to match the higher "
                "resistance (firmware package BMS-FW-7.4.2 or later).",
                "4. Verification: After re-energizing, run a scheduled ramp and confirm no ERR_PRE_003 alarm "
                "within 15 minutes."]),
        ],
        "table_title": "Specification Changes",
        "table": [["Parameter", "Before ECO-2026-077", "After ECO-2026-077"],
                  ["Pre-charge resistor", "RES-PR-50 (50 ohm, 200 W)", "RES-PR-75 (75 ohm, 300 W)"],
                  ["Terminal torque", "4.5 N m", "6.0 N m"],
                  ["BMS pre-charge timeout", "4.0 s", "5.5 s"],
                  ["Acceptance resistance band", "47 to 53 ohm", "71 to 79 ohm"],
                  ["Retrofit kit", "-", "KIT-X7-077"]],
        "after_table": ("Field Deployment Plan", [
            "Field technicians performing scheduled preventive maintenance must install retrofit kit "
            "KIT-X7-077 on all active X-7000 units with serial numbers between SN-X7-0001 and SN-X7-0150.",
            "Estimated technician labour time: 2.0 hours per unit, including the verification ramp.",
            "Warranty coverage: parts and labour for this retrofit are billed under warranty code W-ECO-077 "
            "and must be referenced in the warranty claim notes.",
            "Units outside the serial range already ship with RES-PR-75 from the November 1, 2026 build onward."]),
        "question": "What does ECO-2026-077 change on the Megapack X-7000 and which units are affected?",
    },
    {
        "file": "GV-INC-2026-131_Field_Incident_Coolant_Pump_Bearing_Failure.pdf",
        "shows": "PowerStation G-3500 field incident: root cause, corrective actions, timeline table",
        "title": "Field Incident Investigation Report: PowerStation G-3500 Coolant Pump Bearing Failure",
        "header": ["Incident Identifier: INC-2026-131",
                   "Platform: Gigavolt PowerStation G-3500 (Model: G-3500)",
                   "Site: Harlow Ridge Solar Storage Facility, Unit Bay 4",
                   "Date of Incident: October 22, 2026",
                   "Lead Investigator: Marcus Ellery, Field Reliability Engineer"],
        "sections": [
            ("Incident Summary", [
                "At 14:37 local time the G-3500 thermal controller raised ERR_COOL_302 (coolant flow below "
                "threshold) followed by an automatic derate to 40 percent output. Coolant flow fell from "
                "the nominal 38 L/min to 11 L/min within 6 minutes. Battery module temperatures peaked at "
                "47.8 C before the derate stabilised the system. No thermal runaway or safety event occurred."]),
            ("Root Cause", [
                "Disassembly of the primary glycol pump (Part Number: PMP-GLY-35A) found a seized rear "
                "ball bearing. Lubricant analysis showed glycol contamination caused by a hardened shaft "
                "seal (Part Number: SEAL-PMP-35). The seal material degrades above 70 C ambient, which this "
                "site exceeded on 19 days during the summer. The pump had 14,200 operating hours, below its "
                "rated 30,000-hour life."]),
            ("Corrective Actions", [
                "1. Replace PMP-GLY-35A with the sealed-bearing pump PMP-GLY-35B on the affected unit.",
                "2. Replace SEAL-PMP-35 with the fluorocarbon seal SEAL-PMP-35V on all G-3500 pumps at "
                "sites with more than 10 days per year above 70 C ambient.",
                "3. Add a monthly pump vibration check; replace the pump if vibration exceeds 7.1 mm/s RMS."]),
        ],
        "table_title": "Incident Timeline (October 22, 2026)",
        "table": [["Time", "Event", "Reading"],
                  ["14:31", "Pump vibration rising", "6.8 mm/s RMS"],
                  ["14:37", "ERR_COOL_302 raised", "Flow 24 L/min"],
                  ["14:40", "Automatic derate to 40 percent", "Flow 15 L/min"],
                  ["14:43", "Peak module temperature", "47.8 C"],
                  ["16:05", "Technician on site, pump isolated", "Flow 0 L/min"]],
        "after_table": ("Fleet Impact", [
            "Estimated affected population: 64 G-3500 units at 7 high-temperature sites.",
            "Estimated labour time for the seal retrofit: 1.5 hours per pump.",
            "Warranty claims for this failure mode must reference incident INC-2026-131."]),
        "question": "What does incident report INC-2026-131 give as the root cause and the corrective action steps for the G-3500 coolant pump failure?",
    },
    {
        "file": "GV-SOP-INSP-715_SOP_Thermal_Imaging_Inspection.pdf",
        "shows": "CompactGrid C-1200 procedure: thermal imaging steps, severity-class table",
        "title": "Standard Operating Procedure: CompactGrid C-1200 Thermal Imaging Inspection",
        "header": ["Procedure Identifier: SOP-INSP-715",
                   "Platform: Gigavolt CompactGrid C-1200 (Model: C-1200)",
                   "Revision: A, effective November 10, 2026",
                   "Required Equipment: Infrared camera with at least 320 x 240 resolution and emissivity "
                   "set to 0.95 (tool ID TOOL-IR-320)",
                   "Owner: Field Service Engineering"],
        "sections": [
            ("Purpose", [
                "This procedure describes how technicians use infrared thermography to find loose "
                "connections and failing components on the C-1200 cassette backplane and DC busbars "
                "before they cause ERR_FUSE_001 or ERR_INV_404 alarms."]),
            ("Procedure", [
                "1. Run the unit at a minimum of 60 percent rated load for at least 20 minutes before imaging.",
                "2. Open the rear service door with the door interlock bypass key KEY-C12-RS; never remove "
                "insulating barriers on an energized unit.",
                "3. Image every busbar joint and cassette receptacle from no closer than 1.0 m.",
                "4. Record the hottest point of each joint and the ambient temperature; calculate the "
                "temperature rise (delta T) above the reference joint.",
                "5. Classify each finding with the severity table and log it in the service record with "
                "the image file name."]),
        ],
        "table_title": "Delta T Severity Classes",
        "table": [["Class", "Delta T above reference", "Required action", "Deadline"],
                  ["IR-1 Advisory", "1 to 5 C", "Re-image at next scheduled visit", "Next visit"],
                  ["IR-2 Intermediate", "5 to 15 C", "Re-torque joint to 8.0 N m and re-image", "30 days"],
                  ["IR-3 Serious", "15 to 35 C", "Replace connector hardware kit KIT-C12-715", "7 days"],
                  ["IR-4 Critical", "above 35 C", "Isolate the cassette immediately and open a dispatch",
                   "Immediately"]],
        "after_table": ("Records", [
            "Every IR-3 and IR-4 finding must be reported to Field Service Engineering within 24 hours.",
            "Thermal images are kept for 5 years with the unit service history."]),
        "question": "In procedure SOP-INSP-715, what action is required for each thermal imaging severity class on the C-1200?",
    },
    {
        "file": "GV-TSB-2026-014_Technical_Service_Bulletin_Firmware_7.5.0.pdf",
        "shows": "a new document type (service bulletin): firmware 7.5.0 for all three models",
        "title": "Technical Service Bulletin: BMS Firmware 7.5.0 Release",
        "header": ["Bulletin Identifier: TSB-2026-014",
                   "Applies to: Megapack X-7000, PowerStation G-3500 and CompactGrid C-1200",
                   "Firmware Package: BMS-FW-7.5.0 (release date November 12, 2026)",
                   "Minimum Previous Version: BMS-FW-7.3.0",
                   "Issued by: Gigavolt Firmware Engineering"],
        "sections": [
            ("Summary", [
                "Firmware 7.5.0 corrects false ERR_SENS_005 sensor faults caused by a timing error in the "
                "cell voltage polling loop, and reduces the cell balancing start threshold from 30 mV to "
                "20 mV. Field data from the 7.5.0 beta on 41 units showed a 63 percent reduction in "
                "ERR_SENS_005 alarms over 30 days."]),
            ("Installation Instructions", [
                "1. Confirm the unit is on BMS-FW-7.3.0 or later; units on older versions must first be "
                "updated to 7.3.0 using SOP-FIRM-105.",
                "2. Schedule the update during a standby window; the update takes about 25 minutes and the "
                "unit cannot dispatch power during this time.",
                "3. Verify the firmware checksum 7F3A-91C2 before flashing.",
                "4. After the update, confirm the BMS reports version 7.5.0 and clear stored ERR_SENS_005 codes."]),
        ],
        "table_title": "Changes by Model",
        "table": [["Model", "Change in 7.5.0", "Update priority"],
                  ["Megapack X-7000", "ERR_SENS_005 fix, balancing threshold 20 mV", "High"],
                  ["PowerStation G-3500", "ERR_SENS_005 fix, coolant pump vibration logging", "High"],
                  ["CompactGrid C-1200", "Balancing threshold 20 mV", "Medium"]],
        "after_table": ("Known Issues", [
            "The front panel may show version 7.4.9 for up to 10 minutes after the update; this is a "
            "display delay only.",
            "Do not downgrade from 7.5.0 to any version below 7.4.0; doing so resets the cell calibration table."]),
        "question": "What does firmware BMS-FW-7.5.0 in TSB-2026-014 fix, and what are the installation steps?",
    },
]

SCANNED = "GV-SOP-SCAN-999_Scanned_Inspection_Checklist.pdf"


def build(spec):
    path = OUT / spec["file"]
    doc = SimpleDocTemplate(str(path), pagesize=LETTER, leftMargin=inch, rightMargin=inch,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                            title=spec["title"], author="Gigavolt (sample demo document)")
    ncols = len(spec["table"][0])
    table = Table(spec["table"], colWidths=[6.5 * inch / ncols] * ncols)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6ecf2")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story = [Paragraph(spec["title"], H1), Spacer(1, 6)] + [Paragraph(line, BODY) for line in spec["header"]]
    for heading, paras in spec["sections"]:
        story += [Paragraph(heading, H2)] + [Paragraph(p, BODY) for p in paras]
    story += [PageBreak(), Paragraph(spec["table_title"], H2), table, Spacer(1, 10)]
    heading, bullets = spec["after_table"]
    story += [Paragraph(heading, H2)] + [Paragraph("- " + b, BODY) for b in bullets]   # "-" not a bullet glyph:
    doc.build(story)                                                                   # pdfplumber reads it cleanly
    return path


def build_scanned():
    """An image-only page, like a scan with no OCR: there is no text for the chunker to extract."""
    path = OUT / SCANNED
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFillColor(colors.HexColor("#f4f1e8"))
    c.rect(0, 0, *LETTER, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor("#9a9a9a"))
    for i in range(14):                       # checklist boxes and lines drawn as shapes, not text
        y = 680 - i * 42
        c.rect(80, y, 14, 14, stroke=1, fill=0)
        c.line(110, y + 4, 520, y + 4)
    c.save()
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = []
    for spec in DOCS:
        catalog.append({"file": build(spec).name, "shows": spec["shows"], "question": spec["question"]})
    catalog.append({"file": build_scanned().name, "question": None,
                    "shows": "error handling: an image-only scan with no text -> the file is quarantined"})
    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    for i, entry in enumerate(catalog, start=1):
        print(f"{i}. {entry['file']}\n   {entry['shows']}\n   ask: {entry['question']}")


if __name__ == "__main__":
    main()
