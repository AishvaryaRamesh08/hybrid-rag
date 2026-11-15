# CDC trigger overhead

Median of 3 runs, in milliseconds, on copies of service_logs and Audit_Logs. Single-row workloads use 1000 separate autocommitted statements.

| Workload | Without trigger (ms) | With CDC trigger (ms) | Per row without (ms) | Per row with (ms) | Overhead |
|---|---:|---:|---:|---:|---:|
| single-row INSERT | 1286 | 1664 | 1.286 | 1.664 | +29% |
| single-row UPDATE | 1419 | 1895 | 1.419 | 1.895 | +34% |
| bulk INSERT (5,000 rows) | 156 | 305 | 0.031 | 0.061 | +96% |
| bulk no-op upsert (5,000 rows) | 28 | 62 | 0.006 | 0.012 | +119% |

Audit rows written per pass with the trigger: 7000 (1000 inserts + 1000 updates + 5,000 bulk inserts; the no-op upsert wrote none).
