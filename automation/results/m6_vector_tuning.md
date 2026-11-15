# Vector search tuning (HNSW ef_search)

26 benchmark questions as queries, k=5, M=16, ef_construction=50. Recall is measured against exact search over the same vectors.

| Collection | Vectors | ef_search | recall@5 | P50 (ms) | P95 (ms) |
|---|---:|---:|---:|---:|---:|
| gv_manuals | 193 | 10 | 1.000 | 1.07 | 1.14 |
| gv_manuals | 193 | 25 | 1.000 | 1.09 | 1.15 |
| gv_manuals | 193 | 50 | 1.000 | 1.13 | 1.19 |
| gv_manuals | 193 | 100 | 1.000 | 1.15 | 1.22 |
| gv_manuals | 193 | 200 | 1.000 | 1.13 | 1.20 |
| gv_manuals | 193 | 400 | 1.000 | 1.14 | 1.20 |
| gv_erp | 6201 | 10 | 0.392 | 1.10 | 1.19 |
| gv_erp | 6201 | 25 | 0.646 | 1.17 | 1.28 |
| gv_erp | 6201 | 50 | 0.785 | 1.21 | 1.29 |
| gv_erp | 6201 | 100 | 0.862 | 1.32 | 1.47 |
| gv_erp | 6201 | 200 | 0.938 | 1.43 | 1.53 |
| gv_erp | 6201 | 400 | 0.954 | 1.60 | 1.71 |
