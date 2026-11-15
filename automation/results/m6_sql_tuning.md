# SQL tuning: before and after

Median of 200 executions per query, in milliseconds. 'Before' is the Milestone 5 schema and query text; 'after' is with sql/10_index_tuning.sql and the Milestone 6 query text.

| Query | Before (ms) | After (ms) | Speed-up |
|---|---:|---:|---:|
| Unit lookup by ID or serial | 0.891 | 0.258 | 3.5x |
| Unit history, newest first | 0.311 | 0.302 | 1.0x |
| Unit history in a date window | 0.298 | 0.281 | 1.1x |
| Claim lookup (LIKE scan -> primary-key join) | 47.313 | 0.313 | 151.1x |

## Query plans

**Unit lookup by ID or serial**

- before: `eu: type=ALL, key=None, rows=2500, Using where`
- after: `eu: type=index_merge, key=PRIMARY,idx_serial, rows=2, Using union(PRIMARY,idx_serial); Using where`

**Unit history, newest first**

- before: `rag_payloads: type=ref, key=idx_equip, rows=9, Using index condition; Using where; Using filesort`
- after: `rag_payloads: type=ref, key=idx_equip_date, rows=9, Using index condition; Using where`

**Unit history in a date window**

- before: `rag_payloads: type=ref, key=idx_equip, rows=9, Using index condition; Using where; Using filesort`
- after: `rag_payloads: type=range, key=idx_equip_date, rows=3, Using index condition`

**Claim lookup (LIKE scan -> primary-key join)**

- before: `rag_payloads: type=ALL, key=None, rows=5777, Using where`
- after: `rag_payloads: type=range, key=uq_source, rows=2, Using where; Using index; None: type=None, key=None, rows=None, Impossible WHERE noticed after reading const tables; <union1,2>: type=ALL, key=None, rows=None`

