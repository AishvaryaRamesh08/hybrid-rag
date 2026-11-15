#!/bin/bash
# deploy.sh - copy the code from this repository to the EC2 instance.
# Usage (from the repository root):  bash automation/ops/deploy.sh <key.pem> ubuntu@<public-ip>
# The Phase 4 and 5 modules (vector/src, rag) go to /opt/gigavolt/src, where Phase 5 put them;
# the automation code goes to /opt/gigavolt/m6.
set -euo pipefail
KEY=$1; HOST=$2
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ssh -i "$KEY" "$HOST" "mkdir -p /opt/gigavolt/m6 /opt/gigavolt/src"
scp -i "$KEY" "$REPO"/vector/src/*.py "$REPO"/rag/*.py "$REPO"/rag/prompt_template.txt "$HOST":/opt/gigavolt/src/
scp -i "$KEY" -r "$REPO"/automation/{pipeline,rag,bench,ops,sql,demo,requirements.txt} "$HOST":/opt/gigavolt/m6/
echo "Deployed. Next on the instance: cd /opt/gigavolt/m6 && bash ops/setup_m6.sh"
