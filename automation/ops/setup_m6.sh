#!/bin/bash
# =============================================================================
# setup_m6.sh - one-time Milestone 6 setup on the EC2 instance (after the Milestone 5
# system is built). Re-runnable. Run as ubuntu from /opt/gigavolt/m6 with config.env loaded:
#     bash ops/setup_m6.sh
#
#   1. creates the landing folders, the state folder and the results folder
#   2. creates the pipeline tables                     (sql/08_pipeline_tables.sql)
#   3. applies the index tuning                        (sql/10_index_tuning.sql)
#      and installs the CDC triggers                  (sql/11_cdc_triggers.sql)
#   4. runs the pipeline once: with nothing in the landing folders this only records the
#      existing Milestone 5 vectors in rag_vector_sync and runs the integrity check
#   5. installs the systemd timer that runs the pipeline every 10 minutes
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=${GIGAVOLT_ROOT:-/opt/gigavolt}
mkdir -p "$ROOT"/landing/{erp,telemetry,documents} "$ROOT"/{state,logs} results

echo ">>> pipeline tables, index tuning, CDC triggers"
sudo mariadb gigavolt_erp < sql/08_pipeline_tables.sql
sudo mariadb gigavolt_erp < sql/10_index_tuning.sql
sudo mariadb gigavolt_erp < sql/11_cdc_triggers.sql

echo ">>> first pipeline run (bootstrap)"
python pipeline/run_pipeline.py
python pipeline/run_pipeline.py --status | head -16

echo ">>> systemd timer"
sudo cp ops/gigavolt-pipeline.service ops/gigavolt-pipeline.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gigavolt-pipeline.timer
systemctl list-timers gigavolt-pipeline.timer --no-pager | head -3
echo "Milestone 6 setup complete."
