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
BASE_STATE_DIR=".coderlm/codex_state"
CODERLM_PORT="${CODERLM_PORT:-3001}"

# Always create the symlink so the skill can find the CLI,
# even if the server isn't running yet.
mkdir -p "$BASE_STATE_DIR"
ln -sf "$CLI" "$BASE_STATE_DIR/coderlm_cli.py"

# Generate a unique instance ID for this Claude Code session.
# $PPID is the Claude Code process — all Bash commands from this session
# share it as an ancestor, so PID-keyed lookup auto-resolves.
if [ -z "$CODERLM_INSTANCE" ]; then
    CODERLM_INSTANCE=$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')
fi
INSTANCES_DIR="$BASE_STATE_DIR/instances"
mkdir -p "$INSTANCES_DIR"
echo -n "$CODERLM_INSTANCE" > "$INSTANCES_DIR/$PPID"

# Also write active_instance as single-session fallback
echo -n "$CODERLM_INSTANCE" > "$BASE_STATE_DIR/active_instance"

# Clean up stale PID files (processes that no longer exist)
for f in "$INSTANCES_DIR"/*; do
    [ -f "$f" ] || continue
    pid=$(basename "$f")
    if [ "$pid" != "$PPID" ] && ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$f"
    fi
done

# Check server health — if not running, stop here (symlink is set up)
if ! curl -s --max-time 2 "http://127.0.0.1:${CODERLM_PORT}/api/v1/health" > /dev/null 2>&1; then
    echo "[coderlm] Server not running on port ${CODERLM_PORT}" >&2
    exit 0
fi

# Auto-init with instance ID
export CODERLM_INSTANCE
python3 "$CLI" init --port "$CODERLM_PORT" 2>&1 || true

exit 0
