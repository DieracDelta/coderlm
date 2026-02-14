#!/usr/bin/env python3
"""RLM REPL environment for CodeRLM.

Executes Python code with injected helpers that call the coderlm API.
Durable state (buffers, variables) lives on the Rust server -- the Python
namespace is ephemeral (only lasts for a single exec call).

Usage:
  python3 coderlm_repl.py exec --code "print(search('auth'))"
  python3 coderlm_repl.py exec < script.py
  python3 coderlm_repl.py state          # show buffer/var summary from server
  python3 coderlm_repl.py check-final    # check termination
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


# ── Server communication ──────────────────────────────────────────────

def _state_dir() -> Path:
    base = Path(".claude/coderlm_state")
    inst = os.environ.get("CODERLM_INSTANCE")
    if inst:
        return base / "sessions" / inst
    return base


def _load_state() -> dict:
    state_file = _state_dir() / "session.json"
    if not state_file.exists():
        return {}
    with state_file.open() as f:
        return json.load(f)


def _base_url(state: dict) -> str:
    host = state.get("host", "127.0.0.1")
    port = state.get("port", int(os.environ.get("CODERLM_PORT", 3002)))
    return f"http://{host}:{port}/api/v1"


def _session_id(state: dict) -> str:
    sid = state.get("session_id")
    if not sid:
        raise RuntimeError("No active coderlm session. Run: coderlm_cli.py init")
    return sid


def _request(
    method: str,
    url: str,
    data: dict | None = None,
    headers: dict | None = None,
    timeout: int = 30,
) -> dict:
    hdrs = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body_text)
        except json.JSONDecodeError:
            err = {"error": body_text, "status": e.code}
        raise RuntimeError(f"API error {e.code}: {json.dumps(err)}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot connect to coderlm-server: {e.reason}")


def _get(state: dict, path: str, params: dict | None = None) -> dict:
    base = _base_url(state)
    url = f"{base}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return _request("GET", url, headers={"X-Session-Id": _session_id(state)})


def _post(state: dict, path: str, data: dict) -> dict:
    base = _base_url(state)
    url = f"{base}{path}"
    return _request("POST", url, data=data, headers={"X-Session-Id": _session_id(state)})


def _delete(state: dict, path: str) -> dict:
    base = _base_url(state)
    url = f"{base}{path}"
    return _request("DELETE", url, headers={"X-Session-Id": _session_id(state)})


# ── Injected helpers ──────────────────────────────────────────────────
# These are injected into the exec namespace so user code can call them.

_STATE: dict = {}  # loaded once at startup


def search(query: str, limit: int = 20) -> list[dict]:
    """Search symbols by name."""
    result = _get(_STATE, "/symbols/search", {"q": query, "limit": limit})
    return result.get("symbols", [])


def impl_(symbol: str, file: str) -> str:
    """Get full source of a symbol."""
    result = _get(_STATE, "/symbols/implementation", {"symbol": symbol, "file": file})
    return result.get("source", "")


def callers(symbol: str, file: str, limit: int = 50) -> list[dict]:
    """Find call sites for a symbol."""
    result = _get(_STATE, "/symbols/callers", {"symbol": symbol, "file": file, "limit": limit})
    return result.get("callers", [])


def tests(symbol: str, file: str, limit: int = 20) -> list[dict]:
    """Find tests referencing a symbol."""
    result = _get(_STATE, "/symbols/tests", {"symbol": symbol, "file": file, "limit": limit})
    return result.get("tests", [])


def grep(pattern: str, max_matches: int = 50, scope: str = "all") -> list[dict]:
    """Regex search across all files."""
    result = _get(_STATE, "/grep", {"pattern": pattern, "max_matches": max_matches, "scope": scope})
    return result.get("matches", [])


def symbols(file: str | None = None, kind: str | None = None, limit: int = 100) -> list[dict]:
    """List symbols, optionally filtered."""
    params: dict = {"limit": limit}
    if file:
        params["file"] = file
    if kind:
        params["kind"] = kind
    result = _get(_STATE, "/symbols", params)
    return result.get("symbols", [])


def peek_file(file: str, start: int = 0, end: int = 50) -> str:
    """Read a line range from a file."""
    result = _get(_STATE, "/peek", {"file": file, "start": start, "end": end})
    return result.get("content", "")


# ── Buffer management ─────────────────────────────────────────────────

def load_buffer(name: str, file: str, start: int = 0, end: int = 100) -> dict:
    """Load file content into a named buffer."""
    return _post(_STATE, "/buffers/from-file", {"name": name, "file": file, "start": start, "end": end})


def load_symbol(name: str, symbol: str, file: str) -> dict:
    """Load a symbol's source into a named buffer."""
    return _post(_STATE, "/buffers/from-symbol", {"name": name, "symbol": symbol, "file": file})


def create_buffer(name: str, content: str, description: str = "") -> dict:
    """Create a buffer with arbitrary content."""
    return _post(_STATE, "/buffers", {"name": name, "content": content, "description": description})


def peek(name: str, start: int = 0, end: int = 500) -> str:
    """Read a slice of a buffer's content."""
    result = _get(_STATE, f"/buffers/{urllib.parse.quote(name, safe='')}/peek", {"start": start, "end": end})
    return result.get("content", "")


def list_buffers() -> list[dict]:
    """List all buffers (metadata only)."""
    result = _get(_STATE, "/buffers")
    return result.get("buffers", [])


def delete_buffer(name: str) -> None:
    """Delete a buffer."""
    _delete(_STATE, f"/buffers/{urllib.parse.quote(name, safe='')}")


# ── Variable management ───────────────────────────────────────────────

def set_var(name: str, value) -> None:
    """Set a named variable on the server."""
    _post(_STATE, "/vars", {"name": name, "value": value})


def get_var(name: str):
    """Get a variable value from the server."""
    result = _get(_STATE, f"/vars/{urllib.parse.quote(name, safe='')}")
    return result.get("value")


def list_vars() -> list[dict]:
    """List all variables."""
    result = _get(_STATE, "/vars")
    return result.get("variables", [])


# ── RLM control ───────────────────────────────────────────────────────

def set_final(result) -> None:
    """Set the Final variable (Algorithm 1 termination)."""
    set_var("Final", result)


def add_finding(text: str) -> None:
    """Append a finding to the 'findings' variable (list)."""
    try:
        findings = get_var("findings")
        if not isinstance(findings, list):
            findings = [findings]
    except RuntimeError:
        findings = []
    findings.append(text)
    set_var("findings", findings)


def subcall_results() -> list[dict]:
    """Get all stored subcall results."""
    result = _get(_STATE, "/subcall_results")
    return result.get("results", [])


def clear_subcall_results() -> None:
    """Clear all stored subcall results."""
    _delete(_STATE, "/subcall_results")


def llm_query(prompt: str, context: str = "", chunk_id: str = "") -> dict:
    """Delegate a question to a sub-LM via the coderlm-subcall agent.

    Args:
        prompt: The question to answer about the context.
        context: Text to analyze (inline). If empty, prompt should reference
                 a buffer or file to read.
        chunk_id: Identifier for tracking this subcall's result.

    Returns:
        Parsed JSON result dict with findings, suggested_queries, etc.
    """
    import shutil
    import subprocess
    import tempfile

    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise RuntimeError("'claude' CLI not found on PATH. Install Claude Code to use llm_query().")

    # Build the agent file path (relative to plugin root)
    agent_file = Path(__file__).parent.parent.parent.parent / "agents" / "coderlm-subcall.md"
    if not agent_file.exists():
        # Try project-level .claude/agents/
        agent_file = Path(".claude/agents/coderlm-subcall.md")
    if not agent_file.exists():
        raise RuntimeError(
            f"coderlm-subcall agent not found. Expected at: {agent_file}\n"
            "Copy plugin/agents/coderlm-subcall.md to .claude/agents/"
        )

    # Build the prompt for the subagent
    full_prompt = f"Query: {prompt}\n"
    if chunk_id:
        full_prompt += f"Chunk ID: {chunk_id}\n"
    if context:
        full_prompt += f"\n--- CONTEXT ---\n{context}\n--- END CONTEXT ---\n"

    # Write prompt to temp file for large contexts
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(full_prompt)
        prompt_file = f.name

    try:
        result = subprocess.run(
            [
                claude_bin,
                "--print",
                "--output-format", "text",
                "--agent-file", str(agent_file),
                "--prompt", full_prompt,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        os.unlink(prompt_file)

    if result.returncode != 0:
        raise RuntimeError(f"Subagent failed (exit {result.returncode}): {result.stderr[:500]}")

    # Parse the JSON response
    output = result.stdout.strip()
    # Try to extract JSON from the output (subagent might include extra text)
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        # Try to find JSON object in the output
        start = output.find("{")
        end = output.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(output[start:end])
            except json.JSONDecodeError:
                parsed = {
                    "chunk_id": chunk_id or "unknown",
                    "findings": [{"point": output[:500], "evidence": "", "confidence": "low"}],
                    "suggested_queries": [],
                    "answer_if_complete": None,
                }
        else:
            parsed = {
                "chunk_id": chunk_id or "unknown",
                "findings": [{"point": output[:500], "evidence": "", "confidence": "low"}],
                "suggested_queries": [],
                "answer_if_complete": None,
            }

    # Store result on the server
    if not parsed.get("chunk_id"):
        parsed["chunk_id"] = chunk_id or "unknown"
    _post(_STATE, "/subcall_results", {
        "chunk_id": parsed.get("chunk_id", chunk_id),
        "query": prompt,
        "findings": parsed.get("findings", parsed.get("relevant", [])),
        "suggested_queries": parsed.get("suggested_queries", parsed.get("suggested_next_queries", [])),
        "answer_if_complete": parsed.get("answer_if_complete"),
    })

    # Also store as a buffer for later reference
    buffer_name = f"subcall_{parsed.get('chunk_id', chunk_id or 'unknown')}"
    try:
        create_buffer(buffer_name, json.dumps(parsed, indent=2), f"subcall result for: {prompt[:100]}")
    except RuntimeError:
        pass  # non-critical

    return parsed


# ── Exec engine ───────────────────────────────────────────────────────

def _build_namespace() -> dict:
    """Build the namespace dict with all injected helpers."""
    return {
        # Index queries
        "search": search,
        "impl_": impl_,
        "callers": callers,
        "tests": tests,
        "grep": grep,
        "symbols": symbols,
        "peek_file": peek_file,
        # Buffer management
        "load_buffer": load_buffer,
        "load_symbol": load_symbol,
        "create_buffer": create_buffer,
        "peek": peek,
        "list_buffers": list_buffers,
        "delete_buffer": delete_buffer,
        # Variable management
        "set_var": set_var,
        "get_var": get_var,
        "list_vars": list_vars,
        # RLM control
        "set_final": set_final,
        "add_finding": add_finding,
        "llm_query": llm_query,
        "subcall_results": subcall_results,
        "clear_subcall_results": clear_subcall_results,
        # Standard library conveniences
        "json": json,
    }


def run_exec(code: str) -> dict:
    """Execute code in the REPL namespace, capturing stdout/stderr."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    error = None

    namespace = _build_namespace()

    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf
        exec(code, namespace)
    except Exception:
        error = traceback.format_exc()
        stderr_buf.write(error)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    stdout_str = stdout_buf.getvalue()
    stderr_str = stderr_buf.getvalue()

    return {
        "stdout": stdout_str,
        "stderr": stderr_str,
        "error": error,
        "metadata": {
            "stdout_lines": stdout_str.count("\n") + (1 if stdout_str and not stdout_str.endswith("\n") else 0),
            "stdout_preview": stdout_str[:200] + ("..." if len(stdout_str) > 200 else ""),
            "stdout_size": len(stdout_str),
        },
    }


# ── CLI commands ──────────────────────────────────────────────────────

def cmd_exec(args: argparse.Namespace) -> None:
    global _STATE
    _STATE = _load_state()
    if not _STATE.get("session_id"):
        print("ERROR: No active session. Run: coderlm_cli.py init", file=sys.stderr)
        sys.exit(1)

    if args.code:
        code = args.code
    else:
        code = sys.stdin.read()

    result = run_exec(code)
    print(json.dumps(result, indent=2))


def cmd_state(args: argparse.Namespace) -> None:
    global _STATE
    _STATE = _load_state()
    if not _STATE.get("session_id"):
        print("ERROR: No active session. Run: coderlm_cli.py init", file=sys.stderr)
        sys.exit(1)

    buffers = _get(_STATE, "/buffers")
    variables = _get(_STATE, "/vars")
    print(json.dumps({"buffers": buffers, "variables": variables}, indent=2))


def cmd_check_final(args: argparse.Namespace) -> None:
    global _STATE
    _STATE = _load_state()
    if not _STATE.get("session_id"):
        print("ERROR: No active session. Run: coderlm_cli.py init", file=sys.stderr)
        sys.exit(1)

    result = _get(_STATE, "/vars/final")
    print(json.dumps(result, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(
        prog="coderlm_repl",
        description="RLM REPL environment for CodeRLM",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_exec = sub.add_parser("exec", help="Execute Python code in the REPL environment")
    p_exec.add_argument("--code", help="Code to execute (reads stdin if omitted)")
    p_exec.set_defaults(func=cmd_exec)

    p_state = sub.add_parser("state", help="Show buffer/variable summary from server")
    p_state.set_defaults(func=cmd_state)

    p_final = sub.add_parser("check-final", help="Check if Final variable is set")
    p_final.set_defaults(func=cmd_check_final)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
