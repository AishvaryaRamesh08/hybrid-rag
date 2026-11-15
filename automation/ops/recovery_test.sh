#!/bin/bash
# =============================================================================
# recovery_test.sh - shows the system recovering from failures. Run on EC2 from /opt/gigavolt/m6.
#
#   1. Database restart during a pipeline run: MariaDB is stopped for 10 s while the pipeline
#      runs. Connections are retried with exponential backoff, tasks are retried, and the run
#      completes with zero integrity errors.
#   2. Document store outage during a question: MongoDB is stopped. The question is still
#      answered from MariaDB and ChromaDB and the outage is reported. MongoDB is restarted and
#      the same question then uses all three stores again.
#   3. Network interruption to the LLM: Gemini is unreachable for one question. The pipeline
#      returns the retrieved evidence, labelled as such, instead of failing.
# =============================================================================
set -u
cd "$(dirname "$0")/.."
PY=${PY:-python}
QUESTION="What happened to unit SN-X7-0094 and which components were flagged?"
say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }

say "1. MariaDB restart during a pipeline run"
$PY ops/new_data_batch.py >/dev/null && echo "new batch written to the landing folders"
( sleep 2; echo ">>> stopping MariaDB"; sudo systemctl stop mariadb; sleep 10
  echo ">>> starting MariaDB"; sudo systemctl start mariadb ) &
$PY pipeline/run_pipeline.py
STATUS=$?
wait
echo "Pipeline exit code: $STATUS (0 = completed after the restart)"
$PY pipeline/run_pipeline.py --status | head -16

say "2. MongoDB outage during a question"
sudo systemctl stop mongod && echo ">>> MongoDB stopped"
$PY rag/ask.py "$QUESTION"
sudo systemctl start mongod && echo ">>> MongoDB restarted"
sleep 4
$PY rag/ask.py "$QUESTION"

say "3. Gemini unreachable (network interruption)"
$PY rag/ask.py --simulate-llm-outage "$QUESTION"

say "Recovery test complete"
