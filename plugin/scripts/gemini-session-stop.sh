#!/bin/bash
# plugin/scripts/gemini-session-stop.sh
# Save annotations and clean up coderlm session on Stop.
# Called when the session ends — must never block or fail loudly.
# Skipped when CODERLM_SUBCALL=1 (set by llm_query to prevent
# subprocess agents from cleaning up the parent session).

if [ "${CODERLM_SUBCALL:-0}" = "1" ]; then
    exit 0
fi

if [ -z "$GEMINI_PLUGIN_ROOT" ]; then
    GEMINI_PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi

CLI="$GEMINI_PLUGIN_ROOT/skills/coderlm-gemini/scripts/coderlm_cli.py"
CODERLM_PORT="${CODERLM_PORT:-3002}"

# Clean up PID-keyed instance file for this Gemini session
INSTANCES_DIR=".gemini/coderlm_state/instances"
if [ -d "$INSTANCES_DIR" ] && [ -f "$INSTANCES_DIR/$PPID" ]; then
    CODERLM_INSTANCE=$(cat "$INSTANCES_DIR/$PPID")
    export CODERLM_INSTANCE
    rm -f "$INSTANCES_DIR/$PPID"
fi

if curl -s --max-time 2 "http://127.0.0.1:${CODERLM_PORT}/api/v1/health" > /dev/null 2>&1; then
    python3 "$CLI" save-annotations 2>/dev/null || true
    python3 "$CLI" cleanup 2>/dev/null || true
fi
