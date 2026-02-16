#!/bin/bash
# plugin/scripts/session-stop.sh
# Save annotations and clean up coderlm session on Stop.
# Called by the Stop hook — must never block or fail loudly.
# Skipped when CODERLM_SUBCALL=1 (set by llm_query to prevent
# haiku subprocesses from cleaning up the parent session).

if [ "${CODERLM_SUBCALL:-0}" = "1" ]; then
    exit 0
fi

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
CLI="$PLUGIN_ROOT/skills/coderlm/scripts/coderlm_cli.py"
CODERLM_PORT="${CODERLM_PORT:-3001}"

# Clean up PID-keyed instance file for this Claude session
INSTANCES_DIR=".coderlm/codex_state/instances"
if [ -d "$INSTANCES_DIR" ] && [ -f "$INSTANCES_DIR/$PPID" ]; then
    CODERLM_INSTANCE=$(cat "$INSTANCES_DIR/$PPID")
    export CODERLM_INSTANCE
    rm -f "$INSTANCES_DIR/$PPID"
fi

if curl -s --max-time 2 "http://127.0.0.1:${CODERLM_PORT}/api/v1/health" > /dev/null 2>&1; then
    python3 "$CLI" save-annotations 2>/dev/null || true
    python3 "$CLI" cleanup 2>/dev/null || true
fi
