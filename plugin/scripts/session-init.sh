#!/bin/bash
# Set up coderlm CLI symlink and optionally auto-create session.
# Always exits 0 to never block session start.
# Skipped when CODERLM_SUBCALL=1 (haiku subprocesses should not
# re-init or overwrite the parent session).

if [ "${CODERLM_SUBCALL:-0}" = "1" ]; then
    exit 0
fi

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
CLI="$PLUGIN_ROOT/skills/coderlm/scripts/coderlm_cli.py"
BASE_STATE_DIR=".claude/coderlm_state"
CODERLM_PORT="${CODERLM_PORT:-3002}"

# Always create the symlink so the skill can find the CLI,
# even if the server isn't running yet.
mkdir -p "$BASE_STATE_DIR"
ln -sf "$CLI" "$BASE_STATE_DIR/coderlm_cli.py"

# Check server health — if not running, stop here (symlink is set up)
if ! curl -s --max-time 2 "http://127.0.0.1:${CODERLM_PORT}/api/v1/health" > /dev/null 2>&1; then
    echo "[coderlm] Server not running on port ${CODERLM_PORT}" >&2
    exit 0
fi

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
