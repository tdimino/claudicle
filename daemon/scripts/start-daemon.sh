#!/usr/bin/env bash
# Start the Claudicle daemon in a tmux session via tmuxp.
#
# Usage:
#   ./daemon/scripts/start-daemon.sh          # launch new session
#   tmux attach -t kothar-daemon              # attach to running session
#
# Prerequisites:
#   uv pip install tmuxp

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DAEMON_DIR="$(dirname "$SCRIPT_DIR")"
LAYOUT="$DAEMON_DIR/tmux-layout.yaml"

# Ensure the JSONL log file exists so tail -f doesn't fail
touch "$DAEMON_DIR/slack-events.jsonl"

# Kill existing session if running (idempotent restart)
tmux kill-session -t kothar-daemon 2>/dev/null || true

# Launch via tmuxp
cd "$DAEMON_DIR"
tmuxp load "$LAYOUT" -d

echo "Claudicle daemon started in tmux session 'kothar-daemon'"
echo "Attach with: tmux attach -t kothar-daemon"
