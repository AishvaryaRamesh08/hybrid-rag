# env.sh - loads the Python environment and config for non-interactive shells (ssh, cron, nohup)
source /opt/gigavolt_env/bin/activate
set -a; source /opt/gigavolt/config.env; set +a
export TOKENIZERS_PARALLELISM=false HF_HUB_DISABLE_PROGRESS_BARS=1
cd /opt/gigavolt/m6
