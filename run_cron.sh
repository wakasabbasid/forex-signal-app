#!/bin/bash
# Cron runner — logs output to logs/YYYY-MM-DD.log.
# Usage: run_cron.sh vader [--backtest]

set -euo pipefail
cd "$(dirname "$0")"

# Load .env if present (Telegram credentials, etc.)
if [ -f .env ]; then
  set -a; source .env; set +a
fi

ENGINE="${1:-vader}"
MODE="${2:-}"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/$(date +%Y-%m-%d).log"

{
  echo "===== $(date)  engine=${ENGINE}  mode=${MODE:-pipeline} ====="
  if [ "$ENGINE" = "finbert" ]; then
    PYTHON="venv-finbert/bin/python3"
  else
    PYTHON="venv/bin/python3"
  fi
  if [ "$MODE" = "--backtest" ]; then
    "$PYTHON" -m forex_signal.cli --backtest 2>&1
  else
    "$PYTHON" -m forex_signal.cli --engine "$ENGINE" 2>&1
  fi
  echo ""
} >> "$LOGFILE" 2>&1
