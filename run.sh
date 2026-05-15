#!/bin/bash
# Yatagarasu sweep runner (called by launchd or manually)
# Loads .env and runs the sweep

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Determine sweep type from argument or time of day
SWEEP_TYPE="${1:-auto}"
if [ "$SWEEP_TYPE" = "auto" ]; then
    HOUR=$(date +%H)
    if [ "$HOUR" -lt 10 ]; then
        SWEEP_TYPE="full"
    else
        SWEEP_TYPE="light"
    fi
fi

LOG_FILE="$SCRIPT_DIR/yatagarasu.log"

# Use system python3 or venv if available
if [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="/usr/bin/python3"
fi

if [ "$SWEEP_TYPE" = "light" ]; then
    $PYTHON "$SCRIPT_DIR/yatagarasu.py" --light >> "$LOG_FILE" 2>&1
else
    $PYTHON "$SCRIPT_DIR/yatagarasu.py" >> "$LOG_FILE" 2>&1
fi
