#!/bin/bash
# Check if coderlm-server is running and auto-create session.
# Always exits 0 to never block session start.

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
CLI="$PLUGIN_ROOT/skills/coderlm/scripts/coderlm_cli.py"
BASE_STATE_DIR=".claude/coderlm_state"
CODERLM_PORT="${CODERLM_PORT:-3002}"

# Check server health
if ! curl -s --max-time 2 "http://127.0.0.1:${CODERLM_PORT}/api/v1/health" > /dev/null 2>&1; then
    echo "[coderlm] Server not running on port ${CODERLM_PORT}" >&2
    exit 0
fi

# Create symlink so the skill can find the CLI
mkdir -p "$BASE_STATE_DIR"
ln -sf "$CLI" "$BASE_STATE_DIR/coderlm_cli.py"

# Without CODERLM_INSTANCE, use the flat layout (backward compat).
# The CLI's init already reuses valid sessions, so concurrent inits
# for the same project are safe — they converge on one server session.
STATE_FILE="$BASE_STATE_DIR/session.json"
if [ -n "$CODERLM_INSTANCE" ]; then
    STATE_DIR="$BASE_STATE_DIR/sessions/$CODERLM_INSTANCE"
    mkdir -p "$STATE_DIR"
    STATE_FILE="$STATE_DIR/session.json"
fi

# Auto-init if no active session
if [ ! -f "$STATE_FILE" ]; then
    python3 "$CLI" init --port "$CODERLM_PORT" 2>&1 || true
fi

exit 0
