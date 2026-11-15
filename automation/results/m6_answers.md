# Benchmark answers with source provenance

## S1: What is the nominal capacity and nominal cell voltage of the Prismacell LFP cell?

The nominal capacity of the Prismacell LFP cell (Gigavolt Internal P/N: CEL-LFP-280) is 280 Ah measured at 0.5 C discharge and 25 degrees Celsius, and its nominal cell voltage is 3.20 V [S2][S4].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-SPEC-CELL-LFP-08::c000 | GV-SPEC-CELL-LFP-08 Datasheet.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S4 | chromadb.gv_manuals | GV-SPEC-CELL-LFP-08::c001 | GV-SPEC-CELL-LFP-08 Datasheet.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 1/1 factual statements traced. Latency 0.75 s.

## S2: What are the current and voltage ratings of fuse FUS-FAST-600A?

The current rating of fuse FUS-FAST-600A is 600 A RMS [S2][S4].

* The nominal current rating is 600 A RMS [S2][S4].
* The nominal voltage rating is 700 V DC / 1,000 V AC [S2].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-SPEC-FUSE-PYRO-04::c001 | GV-SPEC-FUSE-PYRO-04 Component Specification DC Fuses.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S4 | chromadb.gv_manuals | GV-SPEC-FUSE-PYRO-04::c000 | GV-SPEC-FUSE-PYRO-04 Component Specification DC Fuses.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 3/3 factual statements traced. Latency 0.63 s.

## S3: What is the nominal power output and energy capacity of the Megapack X-7000?

The Megapack X-7000 delivers a nominal power output of 1,750 kW with an energy capacity of 7,000 kWh (7.0 MWh) [S1][S2].

* Model Identifier: X-7000 [S1][S2].
* Nominal Output Power: 1,750 kW [S1].
* Energy Capacity: 7,000 kWh (7.0 MWh) [S1][S2].

| Tag | Source |
|---|---|
| S1 | chromadb.gv_manuals | GV-MAN-X7000-001::c001 | GV-MAN-X7000-001 Manual.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S2 | chromadb.gv_manuals | GV-MAN-X7000-001::c000 | GV-MAN-X7000-001 Manual.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 4/4 factual statements traced. Latency 0.69 s.

## S4: What trigger current fires the ACT-PYRO-1200 pyrofuse, and how fast does it clear the arc?

The ACT-PYRO-1200 pyrofuse is triggered by a 2.0 A DC pulse of 10 ms duration and clears the arc in less than 1.8 ms from the receipt of the command pulse [S4].

| Tag | Source |
|---|---|
| S4 | chromadb.gv_manuals | GV-SPEC-FUSE-PYRO-04::c003 | GV-SPEC-FUSE-PYRO-04 Component Specification DC Fuses.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 1/1 factual statements traced. Latency 0.70 s.

## S5: How far must personnel evacuate during a battery fire emergency?

Personnel must evacuate to a minimum perimeter distance of 100 meters (330 feet) during a battery fire emergency [S1][S3].

* Depress the external emergency stop (E-STOP) push-button located on the northwest exterior cabinet panel [S1][S3].
* Evacuate to a minimum perimeter distance of 100 meters (330 feet) [S1][S3].
* Trip the master substation breaker and isolate the medium-voltage transformer [S2].

| Tag | Source |
|---|---|
| S1 | chromadb.gv_manuals | GV-MAN-X7000-001::c008 | GV-MAN-X7000-001 Manual.pdf p.2 | 2026-11-06T22:09:21+00:00 |
| S2 | chromadb.gv_manuals | GV-SOP-SAFETY-900::c003 | GV-SOP-SAFETY-900 SOP BESS Emergency Response and Fire Safety.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S3 | chromadb.gv_manuals | GV-MAN-X7000-001::c007 | GV-MAN-X7000-001 Manual.pdf p.2 | 2026-11-06T22:09:21+00:00 |

Provenance check: 4/4 factual statements traced. Latency 0.81 s.

## S6: What does fault code ERR_BMS_708 mean and what is the corrective action?

Fault code ERR_BMS_708 is designated as Thermal Runaway Warning with a fatal severity [S2][S3].

* The primary root cause can be coolant flow obstruction, pump failure, or an internal short circuit [S2].
* The corrective action requires the system to engage auto-deluge, evacuate the area, and prohibit any attempt at a restart without engineering recertification [S2].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-MAN-X7000-001::c013 | GV-MAN-X7000-001 Manual.pdf p.3 | 2026-11-06T22:09:21+00:00 |
| S3 | mongodb.bms_telemetry | TLM-90008 | 2025-01-14T09:00:00+00:00 |

Provenance check: 3/3 factual statements traced. Latency 0.70 s.

## T1: Which warranty claims were filed for equipment unit EQ-7171 in 2021?

Two warranty claims were filed for equipment unit EQ-7171 in 2021 [S1][S2][S3].

* Warranty Claim CLM-9599 was filed on 2021-10-19 and is approved, covering part PRT-2136 with a claimed and approved amount of $2291.49 [S2].
* Warranty Claim CLM-10026 was filed on 2021-09-12 and is under review, covering part PRT-2138 with an amount of $1776.70 pending [S3].

| Tag | Source |
|---|---|
| S1 | mariadb.equipment_units | EQ-7171 |
| S2 | mariadb.rag_payloads | CLM-9599 | 2021-10-19 |
| S3 | mariadb.rag_payloads | CLM-10026 | 2021-09-12 |

Provenance check: 3/3 factual statements traced. Latency 0.91 s.

## T2: What happened to unit SN-X7-0094 on 2024-09-28?

Unit SN-X7-0094 experienced a pre-charge resistor failure and an uncontrolled arc flash within Inverter Bay INV-01 during a scheduled high-power ramp on 2024-09-28 [S8][S9].

* Telemetry reading TLM-90001 on 2024-09-28 at 16:00:00 UTC shows the unit in routine standby with no faults at 35.5 C [S4].
* Telemetry reading TLM-90002 on 2024-09-28 at 16:04:10 UTC shows a scheduled high-power ramp initiated at 36.1 C with no faults [S6].
* Telemetry reading TLM-90003 on 2024-09-28 at 16:04:11 UTC shows a pre-charge resistor failure flagged as RES-PR-50 with fault ERR_PRE_003 and a firmware abort failure at 37.0 C [S8].
* Telemetry reading TLM-90004 on 2024-09-28 at 16:04:12 UTC shows an uncontrolled arc flash and DC Overcurrent Trip with fault ERR_INV_404 at 85.0 C, flagging parts CON-MAIN-800, PCB-DRV-3500, and INV-SCR-9901 [S10].
* The incident report confirms an uncontrolled arc flash occurred within Inverter Bay INV-01 during a scheduled high-power ramp from standby to 1,750 kW full export at 16:04:12 CST [S9].
* No ERP record exists for SN-X7-0094 [S1].

| Tag | Source |
|---|---|
| S1 | mariadb.equipment_units | lookup:SN-X7-0094 |
| S4 | mongodb.bms_telemetry | TLM-90001 | 2024-09-28T16:00:00+00:00 |
| S6 | mongodb.bms_telemetry | TLM-90002 | 2024-09-28T16:04:10.500000+00:00 |
| S8 | mongodb.bms_telemetry | TLM-90003 | 2024-09-28T16:04:11.880000+00:00 |
| S9 | chromadb.gv_manuals | GV-INC-2024-104::c001 | GV-INC-2024-104 Field Incident Report Contactor Flashover.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S10 | mongodb.bms_telemetry | TLM-90004 | 2024-09-28T16:04:12.010000+00:00 |

Provenance check: 7/7 factual statements traced. Latency 1.33 s.

## T3: Which fault codes did unit SN-X7-0150 report in September 2026?

Unit SN-X7-0150 reported fault code ERR_FUSE_001 in September 2026 across 18 readings [S2].

* Telemetry summary shows 18 readings of ERR_FUSE_001 on unit SN-X7-0150 from 2026-09-01 to 2026-09-18, including readings TLM-90026, TLM-90036, and TLM-90046 [S2].
* Reading TLM-90026 on 2026-09-01 11:30:00 UTC recorded fault ERR_FUSE_001 with flagged part FUS-FAST-600A and a DC String Fuse Blown note [S4].
* Reading TLM-90036 on 2026-09-02 11:30:00 UTC recorded fault ERR_FUSE_001 with flagged part FUS-FAST-600A and a DC String Fuse Blown note [S6].
* Reading TLM-90046 on 2026-09-03 11:30:00 UTC recorded fault ERR_FUSE_001 with flagged part FUS-FAST-600A and a DC String Fuse Blown note [S8].
* Reading TLM-90056 on 2026-09-04 11:30:00 UTC recorded fault ERR_FUSE_001 with flagged part FUS-FAST-600A and a DC String Fuse Blown note [S10].

| Tag | Source |
|---|---|
| S2 | mongodb.bms_telemetry | aggregate:unit:SN-X7-0150:September 2026 |
| S4 | mongodb.bms_telemetry | TLM-90026 | 2026-09-01T11:30:00+00:00 |
| S6 | mongodb.bms_telemetry | TLM-90036 | 2026-09-02T11:30:00+00:00 |
| S8 | mongodb.bms_telemetry | TLM-90046 | 2026-09-03T11:30:00+00:00 |
| S10 | mongodb.bms_telemetry | TLM-90056 | 2026-09-04T11:30:00+00:00 |

Provenance check: 6/6 factual statements traced. Latency 1.18 s.

## T4: What is the most recent warranty claim for equipment unit EQ-7171?

The most recent warranty claim for equipment unit EQ-7171 is claim CLM-T0106301 filed on 2026-11-14, with a pending status [S3].

- Claim ID: CLM-T0106301 [S3]
- Date filed: 2026-11-14 [S3]
- Part: Solid-State Circuit Breaker Model-C (PRT-2001) [S3]
- Supplier: Supplier-A [S3]
- Claimed amount: $845.00 [S3]
- Approved amount: Pending [S3]
- Status and denial reason: Pending, with no denial reason [S3]
- Recorded dispatch link: DISP-T0106301 [S3]

| Tag | Source |
|---|---|
| S3 | mariadb.rag_payloads | DISP-T0106301 | 2026-11-14 |

Provenance check: 9/9 factual statements traced. Latency 0.98 s.

## T5: When did fault code ERR_COOL_302 first occur, and on which unit?

Fault code ERR_COOL_302 first occurred on 2025-01-14 08:30:00 UTC on unit SN-C12-0055 [S3].

* Telemetry reading TLM-90006 for unit SN-C12-0055 recorded the initial occurrence on 2025-01-14 08:30:00 UTC [S3].
* The mechanism involves low coolant flow rate caused by airlocks, strainer clogs, or impeller cavitation, with manual GV-MAN-X7000-001 for Model X-7000 noting primary root causes as airlock in the glycol manifold, strainer clog, or impeller cavitation [S2][S3].
* Telemetry reading TLM-90006 recorded flagged parts SEN-FL-022 and FLT-GLY-701, a temperature of 55.4 C, and a status warning [S3].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-MAN-X7000-001::c015 | GV-MAN-X7000-001 Manual.pdf p.3 | 2026-11-06T22:09:21+00:00 |
| S3 | mongodb.bms_telemetry | TLM-90006 | 2025-01-14T08:30:00+00:00 |

Provenance check: 4/4 factual statements traced. Latency 1.32 s.

## T6: When was equipment unit EQ-7171 installed, and when does its warranty expire?

Equipment unit EQ-7171 was installed on 2022-07-05 and its warranty expires on 2023-07-05 [S1].

| Tag | Source |
|---|---|
| S1 | mariadb.equipment_units | EQ-7171 |

Provenance check: 1/1 factual statements traced. Latency 0.68 s.

## M1: For the arc flash on unit SN-X7-0094, which components were flagged and what did the incident investigation report?

The incident investigation report states that Megapack unit SN-X7-0094 suffered an uncontrolled arc flash within Inverter Bay INV-01 during a scheduled high-power ramp from standby to 1,750 kW full export [S3][S5].

* The incident occurred at 16:04:12 CST on September 28, 2024, at the Rio Bravo Wind and Solar Hybrid Plant in Pecos County, Texas [S3][S5].
* The high-speed protection circuit tripped upstream 34.5 kV substation recloser REC-34, isolating the unit, and total equipment damage was localized to the DC pre-charge contactor and main line contactor CON-MAIN-800 [S3].
* Telemetry reading TLM-90003 flagged part RES-PR-50 with a pre-charge resistor failure detected and firmware v2.4.08 abort failed [S6].
* Telemetry reading TLM-90004 flagged parts CON-MAIN-800, PCB-DRV-3500, and INV-SCR-9901 with a DC Overcurrent Trip and arc flash detection [S8].
* No personnel injuries occurred [S3].

| Tag | Source |
|---|---|
| S3 | chromadb.gv_manuals | GV-INC-2024-104::c002 | GV-INC-2024-104 Field Incident Report Contactor Flashover.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S5 | chromadb.gv_manuals | GV-INC-2024-104::c001 | GV-INC-2024-104 Field Incident Report Contactor Flashover.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S6 | mongodb.bms_telemetry | TLM-90003 | 2024-09-28T16:04:11.880000+00:00 |
| S8 | mongodb.bms_telemetry | TLM-90004 | 2024-09-28T16:04:12.010000+00:00 |

Provenance check: 6/6 factual statements traced. Latency 1.25 s.

## M2: Which telemetry fault occurs most on X-7000 units, and what corrective action does the X-7000 manual give for it?

The telemetry fault that occurs most on model X-7000 units is ERR_INV_404, with 20 readings [S2].

* Model X-7000 manual GV-MAN-X7000-001 states that the primary root cause of ERR_INV_404 is an inverter commutation failure and line-to-line bridge breakdown [S3].
* The corrective action for ERR_INV_404 in model X-7000 manual GV-MAN-X7000-001 is to inspect Part INV-SCR-9901 thyristor pack and output fuses, and check AC grid synchronization logs [S3].

| Tag | Source |
|---|---|
| S2 | mongodb.bms_telemetry | aggregate:model:X-7000 |
| S3 | chromadb.gv_manuals | GV-MAN-X7000-001::c014 | GV-MAN-X7000-001 Manual.pdf p.3 | 2026-11-06T22:09:21+00:00 |

Provenance check: 3/3 factual statements traced. Latency 0.81 s.

## M3: Show the service history of equipment unit EQ-7171 and the fault patterns seen in telemetry for its model.

The service history for unit EQ-7171 and the fault patterns for model X-7000 are recorded across multiple service events, warranty claims, and telemetry logs [S1][S3][S5][S6][S7][S8][S9][S10][S11].
- Software Update on 2021-06-05 (In Progress): Calibrated inverter output and verified system operating within normal parameters [S10].
- Warranty Claim CLM-10026 filed 2021-09-12 (Under Review): DisplayTech LCD Unit Model-A (PRT-2138) from Supplier-D claimed for $1776.70 with recorded dispatch link DISP-14336 for unit EQ-5220 [S9].
- Warranty Claim CLM-9599 filed 2021-10-19 (Approved): DC Contactor 400A Model-B (PRT-2136) from Supplier-E claimed and approved for $2291.49 with recorded dispatch link DISP-13247 for unit EQ-5905 [S8].
- Warranty Claim CLM-9714 filed 2022-05-04 (Rejected): Thermal Sensor Module Model-C (PRT-2147) from Supplier-B claimed for $522.82, rejected due to unauthorized modification detected, with recorded dispatch link DISP-13115 for unit EQ-5270 [S7].
- Software Update on 2022-05-10 (Pending): Replaced faulty thermal sensor and verified system bus voltage [S6].
- Warranty Claim CLM-9208 filed 2023-08-06 (Pending): Fusing Unit 200A Model-PRO (PRT-2020) from Supplier-B claimed for $4241.79 with recorded dispatch link DISP-13497 for unit EQ-5224 [S5].
- Emergency Repair on 2023-09-28 (Cancelled): Cleaned heat exchanger after an over-temperature alarm [S4].
- Diagnostic on 2026-11-14 (Completed): Inspected pre-charge circuit after ERR_PRE_003 alarm, replaced resistor RES-PR-50, and filed pending warranty claim CLM-T0106301 for Solid-State Circuit Breaker Model-C (PRT-2001) from Supplier-A with claimed amount $845.00 [S3].
- Corrective Maintenance on 2026-11-14 (Pending): Verified inverter bay INV-01 contactor torque after inspection [S2].

| Tag | Source |
|---|---|
| S1 | mariadb.equipment_units | EQ-7171 |
| S2 | mariadb.rag_payloads | DISP-T0106302 | 2026-11-14 |
| S3 | mariadb.rag_payloads | DISP-T0106301 | 2026-11-14 |
| S4 | mariadb.rag_payloads | DISP-10768 | 2023-09-28 |
| S5 | mariadb.rag_payloads | CLM-9208 | 2023-08-06 |
| S6 | mariadb.rag_payloads | DISP-14701 | 2022-05-10 |
| S7 | mariadb.rag_payloads | CLM-9714 | 2022-05-04 |
| S8 | mariadb.rag_payloads | CLM-9599 | 2021-10-19 |
| S9 | mariadb.rag_payloads | CLM-10026 | 2021-09-12 |
| S10 | mariadb.rag_payloads | DISP-14684 | 2021-06-05 |
| S11 | mongodb.bms_telemetry | aggregate:model:X-7000 |

Provenance check: 10/10 factual statements traced. Latency 4.61 s.

## M4: Fault ERR_COOL_302 occurred on C-1200 units: is it covered by warranty, and what proof does the warranty SOP require?

The ERP has no equipment or service records for model C-1200 [S1].

* Fault ERR_COOL_302 is covered if preventative maintenance records show quarterly filter service [S3].
* Coverage is void if air filters FLT-AIR-12 or glycol cartridges FLT-GLY-701 were unserviced for over 12 months [S3].
* The warranty SOP requires telemetry proof of a coolant pump failure or chiller pressure excursion [S3].

| Tag | Source |
|---|---|
| S1 | mariadb.equipment_models | lookup:C-1200 |
| S3 | chromadb.gv_manuals | GV-SOP-WAR-101::c005 | GV-SOP-WAR-101 SOP Field Warranty Claims.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 4/4 factual statements traced. Latency 0.72 s.

## M5: Telemetry flagged part FUS-FAST-600A during ERR_FUSE_001 faults: what are that fuse's ratings?

The nominal and interrupting ratings for fuse FUS-FAST-600A are specified in component documentation [S6][S7].

* Nominal current rating is 600 A RMS [S6][S7].
* Nominal voltage rating is 700 V DC / 1,000 V AC [S6].
* Interrupting rating breaking capacity is 100 kA DC at 700 V DC with a time constant L/R of 10 ms [S6].
* Melting clearing integral I squared t rating is 42,000 A squared s at rated voltage [S6].

| Tag | Source |
|---|---|
| S6 | chromadb.gv_manuals | GV-SPEC-FUSE-PYRO-04::c001 | GV-SPEC-FUSE-PYRO-04 Component Specification DC Fuses.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S7 | chromadb.gv_manuals | GV-SPEC-FUSE-PYRO-04::c000 | GV-SPEC-FUSE-PYRO-04 Component Specification DC Fuses.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 5/5 factual statements traced. Latency 0.86 s.

## M6: What are the most common service resolutions for X-5000 units, and how many X-5000 warranty claims were approved?

The most common service resolutions for X-5000 units include preventive checks, fuse block replacements, and emergency over-temperature dispatches, while 80 warranty claims were approved [S1][S3].

- Performed standard preventive check and updated firmware to v4.2.1 across 206 dispatches (e.g., DISP-10572, DISP-11563, DISP-10294) [S1].
- Replaced burnt fuse block and completed test runs successfully across 203 dispatches (e.g., DISP-10765, DISP-12818, DISP-12713) [S1].
- Cleaned heat exchanger during emergency dispatches for over-temperature alarms across 185 dispatches (e.g., DISP-13324, DISP-13100, DISP-12204) [S1].
- Replaced faulty thermal sensor and verified system bus voltage across 177 dispatches (e.g., DISP-11450, DISP-11158, DISP-12255) [S1].
- Calibrated inverter output with the system operating within normal parameters across 175 dispatches (e.g., DISP-11725, DISP-13908, DISP-10110) [S1].
- A total of 80 claims were approved for X-5000 units, amounting to $176134.74 claimed [S3].

| Tag | Source |
|---|---|
| S1 | mariadb.service_logs | aggregate:resolutions:X-5000 |
| S3 | mariadb.equipment_units+warranty_claims | aggregate:fleet:X-5000 |

Provenance check: 7/7 factual statements traced. Latency 1.34 s.

## C1: Which suppliers provide lithium cells for our commercial energy storage units?

Suppliers that provide lithium cells for commercial energy storage units include SinoPower Cell Foundry (SUP-SPC-11), Aura Energy Storage Ltd. (SUP-AUR-04), and Voltaic Core Technologies (SUP-VCT-01) [S2][S6][S10].

* SinoPower Cell Foundry supplies Prismacell 280Ah raw cells (CEL-LFP-280) as a Tier-2 cell manufacturer [S2].
* Aura Energy Storage Ltd. (Supplier ID: SUP-AUR-04) fabricates the CobaltMax 65Ah NMC-811 Pouch Cell (CEL-NMC-065) deployed in the PowerStation G-3500 commercial energy storage unit [S8].
* Voltaic Core Technologies (SUP-VCT-01) manufactures the Prismacell 280Ah LiFePO4 cell (CEL-LFP-280), which is utilized in Megapack X-7000 and CompactGrid C-1200 battery modules [S10].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-SUP-REP-401::c002 | GV-SUP-REP-401 Supply Chain Integration Brief.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S6 | chromadb.gv_manuals | GV-SPEC-CELL-NMC-65::c001 | GV-SPEC-CELL-NMC-65 Datasheet.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S8 | chromadb.gv_manuals | GV-SPEC-CELL-NMC-65::c000 | GV-SPEC-CELL-NMC-65 Datasheet.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S10 | chromadb.gv_manuals | GV-SPEC-CELL-LFP-08::c000 | GV-SPEC-CELL-LFP-08 Datasheet.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 4/4 factual statements traced. Latency 0.93 s.

## C2: Which supplier makes the NMC cells used in the PowerStation G-3500?

The Tier-2 pouch cell fabricator Apex Cell Tech Corp (SUP-ACT-07) makes the NMC cells used in the PowerStation G-3500 [S2][S4][S6].

* The CobaltMax 65Ah NMC-811 pouch cell (Gigavolt Internal P/N: CEL-NMC-065) is deployed strictly within the PowerStation G-3500 commercial energy storage unit [S6].
* This cell is fabricated by Tier-1 supplier Aura Energy Storage Ltd. (Supplier ID: SUP-AUR-04) [S6], which is supplied with 24V NMC pouch modules and thermal gap filler pads by the Tier-2 Pouch Cell Fabricator Apex Cell Tech Corp (SUP-ACT-07) [S2][S4].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-SUP-REP-401::c004 | GV-SUP-REP-401 Supply Chain Integration Brief.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S4 | chromadb.gv_manuals | GV-SUP-REP-401::c003 | GV-SUP-REP-401 Supply Chain Integration Brief.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S6 | chromadb.gv_manuals | GV-SPEC-CELL-NMC-65::c000 | GV-SPEC-CELL-NMC-65 Datasheet.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 3/3 factual statements traced. Latency 0.77 s.

## C3: Which supplier is a critical sole-source risk for the inverter gate drive PCB, and what is the mitigation?

Semicon Dynamics Inc. is the critical sole-source risk for the inverter gate drive PCB, and the mitigation involves a redesign project to utilize discrete automotive-grade microcontrollers [S2].

* The Inverter Gate Drive PCB (Part Number PCB-DRV-3500) has an upstream vulnerability of a sole-source custom ASIC gate driver chip with a 26-week foundry lead time [S2].
* Its primary Tier-1/Tier-2 supplier is Semicon Dynamics Inc., also referred to by the code SUP-SDI-09 [S2][S4].
* The secondary supplier alternative mitigation is redesign project ECO-2025-004, which was initiated to utilize discrete automotive-grade microcontrollers [S2].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-SUP-REP-409::c004 | GV-SUP-REP-409 Supply Chain Risk Assessment.pdf p.2 | 2026-11-06T22:09:21+00:00 |
| S4 | chromadb.gv_manuals | GV-SUP-REP-401::c005 | GV-SUP-REP-401 Supply Chain Integration Brief.pdf p.2 | 2026-11-06T22:09:21+00:00 |

Provenance check: 4/4 factual statements traced. Latency 0.88 s.

## C4: What did the supplier quality audit of SinoPower Cell Foundry find?

The supplier quality audit of SinoPower Cell Foundry assessed the Tier-2 SinoPower Cell Foundry QA at Plant 2, High-Tech Industrial Park, Hefei, Anhui Province under Audit Tracking ID AUD-2024-SPC-02 [S4].
* Aris Thorne, Director of Global Quality Assurance [S2][S4].
* The target component of the audit was the Prismacell 280Ah LiFePO₄ Cell (CEL-LFP-280) [S2][S4].
* The audit was conducted across SinoPower's Plant 2 manufacturing lines following elevated field reports of cell voltage divergence (ERR_BMS_701) in Megapack X-7000 modules [S2].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-SUP-AUD-502::c001 | GV-SUP-AUD-502 Quality Audit Report QA Assessment.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S4 | chromadb.gv_manuals | GV-SUP-AUD-502::c000 | GV-SUP-AUD-502 Quality Audit Report QA Assessment.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 4/4 factual statements traced. Latency 1.75 s.

## C5: Which suppliers in our parts catalog supply lithium cell modules?

Suppliers in our parts catalog that supply lithium cell modules include Supplier-C, Supplier-E, Supplier-A, Supplier-B, and Supplier-D [S1][S3][S5][S7][S9].

* Supplier-C supplies Lithium Cell Module 48V Model-A (PRT-2009) and Lithium Cell Module 48V Model-PRO (PRT-2090) [S1].
* Supplier-E supplies Lithium Cell Module 48V Model-A (PRT-2143) and Lithium Cell Module 48V Model-A (PRT-2053), as well as Lithium Cell Module 48V Model-PRO (PRT-2120) [S3].
* Supplier-A supplies Lithium Cell Module 48V Model-MAX (PRT-2024) [S5].
* Supplier-B supplies Lithium Cell Module 48V Model-B (PRT-2041) [S7].
* Supplier-D supplies Lithium Cell Module 48V Model-C (PRT-2115) and Lithium Cell Module 48V Model-MAX (PRT-2087) [S9].

| Tag | Source |
|---|---|
| S1 | mariadb.parts_inventory | aggregate:supplier:Supplier-C |
| S3 | mariadb.parts_inventory | aggregate:supplier:Supplier-E |
| S5 | mariadb.parts_inventory | aggregate:supplier:Supplier-A |
| S7 | mariadb.parts_inventory | aggregate:supplier:Supplier-B |
| S9 | mariadb.parts_inventory | aggregate:supplier:Supplier-D |

Provenance check: 6/6 factual statements traced. Latency 1.09 s.

## C6: Who is the Tier-2 cell manufacturer for the Prismacell 280Ah cell, and what secondary supplier is being qualified?

The Tier-2 cell manufacturer for the Prismacell 280Ah cell is SinoPower Cell Foundry (SUP-SPC-11), and EVE Energy Corp. (P/N: CEL-LFP-280-EV, ISO 9001 certified) is listed as a secondary supplier alternative [S2][S6].

* The Prismacell 280Ah raw cells (CEL-LFP-280) are supplied by Tier-2 Cell Manufacturer SinoPower Cell Foundry (SUP-SPC-11) [S2].
* The secondary supplier alternative for the Prismacell 280Ah LFP Cell (CEL-LFP-280) is EVE Energy Corp. (P/N: CEL-LFP-280-EV, ISO 9001 certified) [S6].

| Tag | Source |
|---|---|
| S2 | chromadb.gv_manuals | GV-SUP-REP-401::c002 | GV-SUP-REP-401 Supply Chain Integration Brief.pdf p.1 | 2026-11-06T22:09:21+00:00 |
| S6 | chromadb.gv_manuals | GV-SUP-REP-409::c003 | GV-SUP-REP-409 Supply Chain Risk Assessment.pdf p.1 | 2026-11-06T22:09:21+00:00 |

Provenance check: 3/3 factual statements traced. Latency 0.93 s.

## G1: What was Gigavolt's total revenue last quarter?

The available records do not show Gigavolt's total revenue last quarter [S1][S2][S3].

| Tag | Source |
|---|---|

Provenance check: 0/0 factual statements traced. Latency 0.53 s.

## G2: Show me service history for equipment unit SN-4829 and related warranty claims

The service and warranty history for equipment unit SN-4829 shows no ERP records or related claims exist [S1].

* No ERP record exists for SN-4829 because equipment_units has no matching equipment_id or serial_number [S1].
* Unit SN-4829 has 18 telemetry readings in total and none has a fault code [S2].
* Telemetry reading TLM-90178 on 2026-09-16 12:15:00 UTC shows Unit SN-4829 (Model G-3500) in status STANDBY with fault none, severity Info, 800 V, 0 A, 31.0 C, SOC 95.0%, delta 9 mV, and flagged parts none [S8].
* Telemetry reading TLM-90188 on 2026-09-17 12:15:00 UTC shows Unit SN-4829 (Model G-3500) in status STANDBY with fault none, severity Info, 800 V, 0 A, 31.0 C, SOC 95.0%, delta 9 mV, and flagged parts none [S6].
* Telemetry reading TLM-90198 on 2026-09-18 12:15:00 UTC shows Unit SN-4829 (Model G-3500) in status STANDBY with fault none, severity Info, 800 V, 0 A, 31.0 C, SOC 95.0%, delta 9 mV, and flagged parts none [S4].

| Tag | Source |
|---|---|
| S1 | mariadb.equipment_units | lookup:SN-4829 |
| S2 | mongodb.bms_telemetry | aggregate:unit:SN-4829 |
| S4 | mongodb.bms_telemetry | TLM-90198 | 2026-09-18T12:15:00+00:00 |
| S6 | mongodb.bms_telemetry | TLM-90188 | 2026-09-17T12:15:00+00:00 |
| S8 | mongodb.bms_telemetry | TLM-90178 | 2026-09-16T12:15:00+00:00 |

Provenance check: 6/6 factual statements traced. Latency 1.30 s.
