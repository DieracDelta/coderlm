#!/usr/bin/env python3
"""CLI wrapper for the coderlm-server API.

Manages session state and provides clean commands for codebase exploration.
All state is cached in .claude/coderlm_state/session.json relative to cwd.

Usage:
  python3 coderlm_cli.py init [--port PORT] [--cwd PATH]
  python3 coderlm_cli.py structure [--depth N]
  python3 coderlm_cli.py symbols [--kind KIND] [--file FILE] [--limit N]
  python3 coderlm_cli.py search QUERY [--limit N]
  python3 coderlm_cli.py impl SYMBOL --file FILE
  python3 coderlm_cli.py callers SYMBOL --file FILE [--limit N]
  python3 coderlm_cli.py tests SYMBOL --file FILE [--limit N]
  python3 coderlm_cli.py variables FUNCTION --file FILE
  python3 coderlm_cli.py peek FILE [--start N] [--end N]
  python3 coderlm_cli.py grep PATTERN [--max-matches N] [--context-lines N] [--scope all|code]
  python3 coderlm_cli.py chunks FILE [--size N] [--overlap N]
  python3 coderlm_cli.py define-file FILE DEFINITION
  python3 coderlm_cli.py redefine-file FILE DEFINITION
  python3 coderlm_cli.py define-symbol SYMBOL --file FILE DEFINITION
  python3 coderlm_cli.py redefine-symbol SYMBOL --file FILE DEFINITION
  python3 coderlm_cli.py mark FILE TYPE
  python3 coderlm_cli.py save-annotations
  python3 coderlm_cli.py load-annotations
  python3 coderlm_cli.py history [--limit N]
  python3 coderlm_cli.py status
  python3 coderlm_cli.py buffer-list
  python3 coderlm_cli.py buffer-create NAME "content" [--description "..."]
  python3 coderlm_cli.py buffer-from-file NAME FILE [--start N] [--end N]
  python3 coderlm_cli.py buffer-from-symbol NAME SYMBOL --file FILE
  python3 coderlm_cli.py buffer-info NAME
  python3 coderlm_cli.py buffer-peek NAME [--start N] [--end N]
  python3 coderlm_cli.py buffer-delete NAME
  python3 coderlm_cli.py var-list
  python3 coderlm_cli.py var-set NAME 'json_value'
  python3 coderlm_cli.py var-get NAME
  python3 coderlm_cli.py var-delete NAME
  python3 coderlm_cli.py check-final
  python3 coderlm_cli.py semantic-chunks FILE [--max-chunk-bytes 5000]
  python3 coderlm_cli.py repl --code "print(search('auth'))"
  python3 coderlm_cli.py cleanup
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

def _state_dir() -> Path:
    """Return per-instance state directory.

    If CODERLM_INSTANCE is set (e.g. by session-init.sh), each Claude Code
    instance gets its own subdirectory so concurrent sessions in the same
    project don't clobber each other.  Falls back to the flat layout for
    backward compat.
    """
    base = Path(".claude/coderlm_state")
    inst = os.environ.get("CODERLM_INSTANCE")
    if inst:
        return base / "sessions" / inst
    return base


STATE_DIR = _state_dir()
STATE_FILE = STATE_DIR / "session.json"


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    with STATE_FILE.open() as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w") as f:
        json.dump(state, f, indent=2)


def _clear_state() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def _base_url(state: dict) -> str:
    host = state.get("host", "127.0.0.1")
    port = state.get("port", int(os.environ.get("CODERLM_PORT", 3002)))
    return f"http://{host}:{port}/api/v1"


def _session_id(state: dict) -> str:
    sid = state.get("session_id")
    if not sid:
        print("ERROR: No active session. Run: coderlm_cli.py init", file=sys.stderr)
        sys.exit(1)
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

        if e.code == 410:
            print(
                "ERROR: Project was evicted from server. Run: coderlm_cli.py init",
                file=sys.stderr,
            )
            _clear_state()
            sys.exit(1)

        print(json.dumps(err, indent=2))
        sys.exit(1)
    except urllib.error.URLError as e:
        print(
            f"ERROR: Cannot connect to coderlm-server: {e.reason}\n"
            f"Make sure the server is running: coderlm-server serve",
            file=sys.stderr,
        )
        sys.exit(1)


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


def _delete_req(state: dict, path: str) -> dict:
    base = _base_url(state)
    url = f"{base}{path}"
    return _request("DELETE", url, headers={"X-Session-Id": _session_id(state)})


def _output(result: dict) -> None:
    print(json.dumps(result, indent=2))


# ── Commands ──────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> None:
    cwd = os.path.abspath(args.cwd or os.getcwd())
    host = args.host or "127.0.0.1"
    port = args.port or int(os.environ.get("CODERLM_PORT", 3002))
    base = f"http://{host}:{port}/api/v1"

    # Check server health first
    try:
        health = _request("GET", f"{base}/health")
    except SystemExit:
        return

    # Reuse existing session if it's still valid on the server
    existing = _load_state()
    if existing.get("session_id") and existing.get("project") == cwd:
        sid = existing["session_id"]
        try:
            _request("GET", f"{base}/sessions/{sid}")
            print(f"Session reused: {sid}")
            print(f"Project: {cwd}")
            print(f"Server: {health.get('status', 'ok')} "
                  f"({health.get('projects', 0)} projects, "
                  f"{health.get('active_sessions', 0)} sessions)")
            return
        except SystemExit:
            pass  # session expired or invalid, create a new one

    # Create session
    result = _request("POST", f"{base}/sessions", data={"cwd": cwd})
    state = {
        "session_id": result["session_id"],
        "host": host,
        "port": port,
        "project": cwd,
        "created_at": result.get("created_at", ""),
    }
    _save_state(state)

    print(f"Session created: {result['session_id']}")
    print(f"Project: {cwd}")
    print(f"Server: {health.get('status', 'ok')} "
          f"({health.get('projects', 0)} projects, "
          f"{health.get('active_sessions', 0)} sessions)")


def cmd_status(args: argparse.Namespace) -> None:
    state = _load_state()
    if not state:
        # No session — just check server health
        host = args.host or "127.0.0.1"
        port = args.port or int(os.environ.get("CODERLM_PORT", 3002))
        base = f"http://{host}:{port}/api/v1"
        result = _request("GET", f"{base}/health")
        _output(result)
        return

    base = _base_url(state)
    health = _request("GET", f"{base}/health")
    info = {"server": health, "session": state}

    # Try to get session details
    sid = state.get("session_id")
    if sid:
        try:
            session_info = _request(
                "GET",
                f"{base}/sessions/{sid}",
            )
            info["session_details"] = session_info
        except SystemExit:
            info["session_details"] = "session may have expired"

    _output(info)


def cmd_structure(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {}
    if args.depth is not None:
        params["depth"] = args.depth
    if not args.full:
        params["meta"] = "true"
    _output(_get(state, "/structure", params))


def cmd_symbols(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {}
    if args.kind:
        params["kind"] = args.kind
    if args.file:
        params["file"] = args.file
    if args.limit is not None:
        params["limit"] = args.limit
    _output(_get(state, "/symbols", params))


def cmd_search(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"q": args.query}
    if args.limit is not None:
        params["limit"] = args.limit
    _output(_get(state, "/symbols/search", params))


def cmd_impl(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"symbol": args.symbol, "file": args.file}
    if not args.full:
        params["meta"] = "true"
    _output(_get(state, "/symbols/implementation", params))


def cmd_callers(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"symbol": args.symbol, "file": args.file}
    if args.limit is not None:
        params["limit"] = args.limit
    if not args.full:
        params["meta"] = "true"
    _output(_get(state, "/symbols/callers", params))


def cmd_tests(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"symbol": args.symbol, "file": args.file}
    if args.limit is not None:
        params["limit"] = args.limit
    if not args.full:
        params["meta"] = "true"
    _output(_get(state, "/symbols/tests", params))


def cmd_variables(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"function": args.function, "file": args.file}
    _output(_get(state, "/symbols/variables", params))


def cmd_peek(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"file": args.file}
    if args.start is not None:
        params["start"] = args.start
    if args.end is not None:
        params["end"] = args.end
    if not args.full:
        params["meta"] = "true"
    _output(_get(state, "/peek", params))


def cmd_grep(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"pattern": args.pattern}
    if args.max_matches is not None:
        params["max_matches"] = args.max_matches
    if args.context_lines is not None:
        params["context_lines"] = args.context_lines
    if args.scope is not None:
        params["scope"] = args.scope
    if not args.full:
        params["meta"] = "true"
    _output(_get(state, "/grep", params))


def cmd_chunks(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"file": args.file}
    if args.size is not None:
        params["size"] = args.size
    if args.overlap is not None:
        params["overlap"] = args.overlap
    _output(_get(state, "/chunk_indices", params))


def cmd_define_file(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/structure/define", {
        "file": args.file,
        "definition": args.definition,
    }))


def cmd_redefine_file(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/structure/redefine", {
        "file": args.file,
        "definition": args.definition,
    }))


def cmd_define_symbol(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/symbols/define", {
        "symbol": args.symbol,
        "file": args.file,
        "definition": args.definition,
    }))


def cmd_redefine_symbol(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/symbols/redefine", {
        "symbol": args.symbol,
        "file": args.file,
        "definition": args.definition,
    }))


def cmd_mark(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/structure/mark", {
        "file": args.file,
        "mark": args.type,
    }))


def cmd_history(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {}
    if args.limit is not None:
        params["limit"] = args.limit
    _output(_get(state, "/history", params))


def cmd_save_annotations(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/annotations/save", {}))


def cmd_load_annotations(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/annotations/load", {}))


# ── History compaction & context budget ─────────────────────────────────


def cmd_compact_history(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {}
    if args.keep_recent is not None:
        params["keep_recent"] = args.keep_recent
    _output(_post_with_params(state, "/history/compact", params))


def cmd_context_budget(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_get(state, "/context_budget"))


def _post_with_params(state: dict, path: str, params: dict) -> dict:
    """POST with query parameters (for compact endpoint)."""
    base = _base_url(state)
    url = f"{base}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return _request("POST", url, headers={"X-Session-Id": _session_id(state)})


# ── Buffer commands ────────────────────────────────────────────────────


def cmd_buffer_list(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_get(state, "/buffers"))


def cmd_buffer_create(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/buffers", {
        "name": args.name,
        "content": args.content,
        "description": args.description or "",
    }))


def cmd_buffer_from_file(args: argparse.Namespace) -> None:
    state = _load_state()
    data: dict = {"name": args.name, "file": args.file}
    if args.start is not None:
        data["start"] = args.start
    if args.end is not None:
        data["end"] = args.end
    _output(_post(state, "/buffers/from-file", data))


def cmd_buffer_from_symbol(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_post(state, "/buffers/from-symbol", {
        "name": args.name,
        "symbol": args.symbol,
        "file": args.file,
    }))


def cmd_buffer_info(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_get(state, f"/buffers/{urllib.parse.quote(args.name, safe='')}"))


def cmd_buffer_peek(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {}
    if args.start is not None:
        params["start"] = args.start
    if args.end is not None:
        params["end"] = args.end
    _output(_get(state, f"/buffers/{urllib.parse.quote(args.name, safe='')}/peek", params))


def cmd_buffer_delete(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_delete_req(state, f"/buffers/{urllib.parse.quote(args.name, safe='')}"))


# ── Variable commands ─────────────────────────────────────────────────


def cmd_var_list(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_get(state, "/vars"))


def cmd_var_set(args: argparse.Namespace) -> None:
    state = _load_state()
    try:
        value = json.loads(args.value)
    except json.JSONDecodeError:
        # Treat as string if not valid JSON
        value = args.value
    _output(_post(state, "/vars", {"name": args.name, "value": value}))


def cmd_var_get(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_get(state, f"/vars/{urllib.parse.quote(args.name, safe='')}"))


def cmd_var_delete(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_delete_req(state, f"/vars/{urllib.parse.quote(args.name, safe='')}"))


def cmd_check_final(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_get(state, "/vars/final"))


# ── Semantic chunks ───────────────────────────────────────────────────


def cmd_semantic_chunks(args: argparse.Namespace) -> None:
    state = _load_state()
    params = {"file": args.file}
    if args.max_chunk_bytes is not None:
        params["max_chunk_bytes"] = args.max_chunk_bytes
    _output(_get(state, "/semantic_chunks", params))


# ── REPL ──────────────────────────────────────────────────────────────


def cmd_repl(args: argparse.Namespace) -> None:
    """Execute code in the REPL environment by spawning coderlm_repl.py."""
    import subprocess
    repl_script = Path(__file__).resolve().parent / "coderlm_repl.py"
    cmd = [sys.executable, str(repl_script), "exec"]
    if args.code:
        cmd.extend(["--code", args.code])
    result = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


# ── Subcall results ───────────────────────────────────────────────────


def cmd_subcall_results(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_get(state, "/subcall_results"))


def cmd_clear_subcall_results(args: argparse.Namespace) -> None:
    state = _load_state()
    _output(_delete_req(state, "/subcall_results"))


def cmd_subcall_batch(args: argparse.Namespace) -> None:
    """Run llm_query on each semantic chunk of a file."""
    import subprocess
    state = _load_state()

    # Get semantic chunks
    params = {"file": args.file}
    if args.max_chunk_bytes is not None:
        params["max_chunk_bytes"] = args.max_chunk_bytes
    chunks_resp = _get(state, "/semantic_chunks", params)
    chunks = chunks_resp.get("chunks", [])

    print(f"Processing {len(chunks)} chunks for {args.file}...", file=sys.stderr)

    repl_script = Path(__file__).resolve().parent / "coderlm_repl.py"
    results = []

    for chunk in chunks:
        chunk_id = f"{args.file}_chunk_{chunk['index']}"
        # Load chunk into buffer
        buf_name = f"chunk_{chunk['index']}"
        _post(state, "/buffers/from-file", {
            "name": buf_name,
            "file": args.file,
            "start": chunk["line_start"],
            "end": chunk["line_end"],
        })

        # Get full buffer content for the subcall
        peek_resp = _get(
            state,
            f"/buffers/{urllib.parse.quote(buf_name, safe='')}/peek",
        )
        content = peek_resp.get("content", "")

        # Run llm_query via REPL
        code = (
            f"result = llm_query("
            f"{json.dumps(args.query)}, "
            f"context={json.dumps(content)}, "
            f"chunk_id={json.dumps(chunk_id)})\n"
            f"print(json.dumps(result, indent=2))"
        )
        proc = subprocess.run(
            [sys.executable, str(repl_script), "exec", "--code", code],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if proc.returncode == 0:
            try:
                exec_result = json.loads(proc.stdout)
                stdout = exec_result.get("stdout", "")
                try:
                    parsed = json.loads(stdout)
                    results.append(parsed)
                    findings_count = len(parsed.get("findings", []))
                    print(
                        f"  chunk {chunk['index']}: {findings_count} findings",
                        file=sys.stderr,
                    )
                except json.JSONDecodeError:
                    print(
                        f"  chunk {chunk['index']}: completed (non-JSON output)",
                        file=sys.stderr,
                    )
            except json.JSONDecodeError:
                print(f"  chunk {chunk['index']}: error parsing exec output", file=sys.stderr)
        else:
            print(f"  chunk {chunk['index']}: FAILED ({proc.stderr[:200]})", file=sys.stderr)

    # Store aggregated results as a variable
    _post(state, "/vars", {"name": "subcall_batch_results", "value": results})

    print(f"\nDone. {len(results)} chunks processed.", file=sys.stderr)
    print(f"Results stored in 'subcall_batch_results' variable.", file=sys.stderr)
    _output({"results": results, "count": len(results)})


def cmd_cleanup(args: argparse.Namespace) -> None:
    state = _load_state()
    if not state.get("session_id"):
        print("No active session.")
        return

    base = _base_url(state)
    sid = state["session_id"]
    result = _request("DELETE", f"{base}/sessions/{sid}")
    _clear_state()
    print(f"Session {sid} deleted.")


# ── Parser ────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="coderlm_cli",
        description="CLI wrapper for coderlm-server API",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    # init
    p_init = sub.add_parser("init", help="Create a session for the current project")
    p_init.add_argument("--cwd", help="Project directory (default: $PWD)")
    p_init.add_argument("--host", default=None, help="Server host (default: 127.0.0.1)")
    p_init.add_argument("--port", type=int, default=None, help="Server port (default: $CODERLM_PORT or 3002)")
    p_init.set_defaults(func=cmd_init)

    # status
    p_status = sub.add_parser("status", help="Show server and session status")
    p_status.add_argument("--host", default=None)
    p_status.add_argument("--port", type=int, default=None)
    p_status.set_defaults(func=cmd_status)

    # structure
    p_struct = sub.add_parser("structure", help="Get project file tree")
    p_struct.add_argument("--depth", type=int, default=None, help="Tree depth (0=unlimited)")
    p_struct.add_argument("--full", action="store_true", help="Return full tree instead of metadata-only")
    p_struct.set_defaults(func=cmd_structure)

    # symbols
    p_sym = sub.add_parser("symbols", help="List symbols")
    p_sym.add_argument("--kind", help="Filter: function, method, class, struct, enum, trait, interface, constant, type, module")
    p_sym.add_argument("--file", help="Filter by file path")
    p_sym.add_argument("--limit", type=int, default=None)
    p_sym.set_defaults(func=cmd_symbols)

    # search
    p_search = sub.add_parser("search", help="Search symbols by name")
    p_search.add_argument("query", help="Search term")
    p_search.add_argument("--limit", type=int, default=None)
    p_search.set_defaults(func=cmd_search)

    # impl
    p_impl = sub.add_parser("impl", help="Get full source of a symbol")
    p_impl.add_argument("symbol", help="Symbol name")
    p_impl.add_argument("--file", required=True, help="File containing the symbol")
    p_impl.add_argument("--full", action="store_true", help="Return full source instead of metadata-only")
    p_impl.set_defaults(func=cmd_impl)

    # callers
    p_callers = sub.add_parser("callers", help="Find call sites for a symbol")
    p_callers.add_argument("symbol", help="Symbol name")
    p_callers.add_argument("--file", required=True, help="File containing the symbol")
    p_callers.add_argument("--limit", type=int, default=None)
    p_callers.add_argument("--full", action="store_true", help="Return full caller text instead of metadata-only")
    p_callers.set_defaults(func=cmd_callers)

    # tests
    p_tests = sub.add_parser("tests", help="Find tests referencing a symbol")
    p_tests.add_argument("symbol", help="Symbol name")
    p_tests.add_argument("--file", required=True, help="File containing the symbol")
    p_tests.add_argument("--limit", type=int, default=None)
    p_tests.add_argument("--full", action="store_true", help="Return full test info instead of metadata-only")
    p_tests.set_defaults(func=cmd_tests)

    # variables
    p_vars = sub.add_parser("variables", help="List local variables in a function")
    p_vars.add_argument("function", help="Function name")
    p_vars.add_argument("--file", required=True, help="File containing the function")
    p_vars.set_defaults(func=cmd_variables)

    # peek
    p_peek = sub.add_parser("peek", help="Read a line range from a file")
    p_peek.add_argument("file", help="File path")
    p_peek.add_argument("--start", type=int, default=None, help="Start line (0-indexed)")
    p_peek.add_argument("--end", type=int, default=None, help="End line (exclusive)")
    p_peek.add_argument("--full", action="store_true", help="Return full content instead of metadata-only")
    p_peek.set_defaults(func=cmd_peek)

    # grep
    p_grep = sub.add_parser("grep", help="Regex search across all files")
    p_grep.add_argument("pattern", help="Regex pattern")
    p_grep.add_argument("--max-matches", type=int, default=None)
    p_grep.add_argument("--context-lines", type=int, default=None)
    p_grep.add_argument("--scope", choices=["all", "code"], default=None,
                         help="Scope filter: 'all' (default) or 'code' (skip comments/strings)")
    p_grep.add_argument("--full", action="store_true", help="Return full match text instead of metadata-only")
    p_grep.set_defaults(func=cmd_grep)

    # chunks
    p_chunks = sub.add_parser("chunks", help="Compute chunk boundaries for a file")
    p_chunks.add_argument("file", help="File path")
    p_chunks.add_argument("--size", type=int, default=None, help="Chunk size in bytes")
    p_chunks.add_argument("--overlap", type=int, default=None, help="Overlap between chunks")
    p_chunks.set_defaults(func=cmd_chunks)

    # define-file
    p_dfile = sub.add_parser("define-file", help="Set a description for a file")
    p_dfile.add_argument("file", help="File path")
    p_dfile.add_argument("definition", help="Human-readable description")
    p_dfile.set_defaults(func=cmd_define_file)

    # redefine-file
    p_rdfile = sub.add_parser("redefine-file", help="Update a file description")
    p_rdfile.add_argument("file", help="File path")
    p_rdfile.add_argument("definition", help="Updated description")
    p_rdfile.set_defaults(func=cmd_redefine_file)

    # define-symbol
    p_dsym = sub.add_parser("define-symbol", help="Set a description for a symbol")
    p_dsym.add_argument("symbol", help="Symbol name")
    p_dsym.add_argument("--file", required=True, help="File containing the symbol")
    p_dsym.add_argument("definition", help="Human-readable description")
    p_dsym.set_defaults(func=cmd_define_symbol)

    # redefine-symbol
    p_rdsym = sub.add_parser("redefine-symbol", help="Update a symbol description")
    p_rdsym.add_argument("symbol", help="Symbol name")
    p_rdsym.add_argument("--file", required=True, help="File containing the symbol")
    p_rdsym.add_argument("definition", help="Updated description")
    p_rdsym.set_defaults(func=cmd_redefine_symbol)

    # mark
    p_mark = sub.add_parser("mark", help="Tag a file with a category")
    p_mark.add_argument("file", help="File path")
    p_mark.add_argument("type", choices=["documentation", "ignore", "test", "config", "generated", "custom"],
                         help="Mark type")
    p_mark.set_defaults(func=cmd_mark)

    # history
    p_hist = sub.add_parser("history", help="Session command history")
    p_hist.add_argument("--limit", type=int, default=None)
    p_hist.set_defaults(func=cmd_history)

    # save-annotations
    p_save = sub.add_parser("save-annotations", help="Save annotations to disk (.coderlm/annotations.json)")
    p_save.set_defaults(func=cmd_save_annotations)

    # load-annotations
    p_load = sub.add_parser("load-annotations", help="Load annotations from disk")
    p_load.set_defaults(func=cmd_load_annotations)

    # buffer-list
    p_bl = sub.add_parser("buffer-list", help="List all buffers (metadata only)")
    p_bl.set_defaults(func=cmd_buffer_list)

    # buffer-create
    p_bc = sub.add_parser("buffer-create", help="Create a buffer from content")
    p_bc.add_argument("name", help="Buffer name")
    p_bc.add_argument("content", help="Buffer content")
    p_bc.add_argument("--description", default=None, help="Buffer description")
    p_bc.set_defaults(func=cmd_buffer_create)

    # buffer-from-file
    p_bff = sub.add_parser("buffer-from-file", help="Load file content into a buffer")
    p_bff.add_argument("name", help="Buffer name")
    p_bff.add_argument("file", help="File path")
    p_bff.add_argument("--start", type=int, default=None, help="Start line (0-indexed)")
    p_bff.add_argument("--end", type=int, default=None, help="End line (exclusive)")
    p_bff.set_defaults(func=cmd_buffer_from_file)

    # buffer-from-symbol
    p_bfs = sub.add_parser("buffer-from-symbol", help="Load symbol source into a buffer")
    p_bfs.add_argument("name", help="Buffer name")
    p_bfs.add_argument("symbol", help="Symbol name")
    p_bfs.add_argument("--file", required=True, help="File containing the symbol")
    p_bfs.set_defaults(func=cmd_buffer_from_symbol)

    # buffer-info
    p_bi = sub.add_parser("buffer-info", help="Get buffer metadata")
    p_bi.add_argument("name", help="Buffer name")
    p_bi.set_defaults(func=cmd_buffer_info)

    # buffer-peek
    p_bp = sub.add_parser("buffer-peek", help="Read a slice of a buffer")
    p_bp.add_argument("name", help="Buffer name")
    p_bp.add_argument("--start", type=int, default=None, help="Start byte offset")
    p_bp.add_argument("--end", type=int, default=None, help="End byte offset")
    p_bp.set_defaults(func=cmd_buffer_peek)

    # buffer-delete
    p_bd = sub.add_parser("buffer-delete", help="Delete a buffer")
    p_bd.add_argument("name", help="Buffer name")
    p_bd.set_defaults(func=cmd_buffer_delete)

    # var-list
    p_vl = sub.add_parser("var-list", help="List all variables")
    p_vl.set_defaults(func=cmd_var_list)

    # var-set
    p_vs = sub.add_parser("var-set", help="Set a variable")
    p_vs.add_argument("name", help="Variable name")
    p_vs.add_argument("value", help="JSON value (or plain string)")
    p_vs.set_defaults(func=cmd_var_set)

    # var-get
    p_vg = sub.add_parser("var-get", help="Get a variable value")
    p_vg.add_argument("name", help="Variable name")
    p_vg.set_defaults(func=cmd_var_get)

    # var-delete
    p_vd = sub.add_parser("var-delete", help="Delete a variable")
    p_vd.add_argument("name", help="Variable name")
    p_vd.set_defaults(func=cmd_var_delete)

    # check-final
    p_cf = sub.add_parser("check-final", help="Check if Final variable is set")
    p_cf.set_defaults(func=cmd_check_final)

    # semantic-chunks
    p_sc = sub.add_parser("semantic-chunks", help="Get symbol-aligned chunks for a file")
    p_sc.add_argument("file", help="File path")
    p_sc.add_argument("--max-chunk-bytes", type=int, default=None, help="Max chunk size in bytes")
    p_sc.set_defaults(func=cmd_semantic_chunks)

    # repl
    p_repl = sub.add_parser("repl", help="Execute code in the RLM REPL environment")
    p_repl.add_argument("--code", help="Code to execute (reads stdin if omitted)")
    p_repl.set_defaults(func=cmd_repl)

    # subcall-results
    p_sr = sub.add_parser("subcall-results", help="List all stored subcall results")
    p_sr.set_defaults(func=cmd_subcall_results)

    # clear-subcall-results
    p_csr = sub.add_parser("clear-subcall-results", help="Clear all stored subcall results")
    p_csr.set_defaults(func=cmd_clear_subcall_results)

    # subcall-batch
    p_sb = sub.add_parser("subcall-batch", help="Run llm_query on each semantic chunk of a file")
    p_sb.add_argument("file", help="File to analyze")
    p_sb.add_argument("query", help="Question to answer about each chunk")
    p_sb.add_argument("--max-chunk-bytes", type=int, default=None, help="Max chunk size in bytes")
    p_sb.set_defaults(func=cmd_subcall_batch)

    # compact-history
    p_ch = sub.add_parser("compact-history", help="Compact session history (group repeated operations)")
    p_ch.add_argument("--keep-recent", type=int, default=None, help="Keep this many recent entries uncompacted")
    p_ch.set_defaults(func=cmd_compact_history)

    # context-budget
    p_cb = sub.add_parser("context-budget", help="Show estimated context budget usage")
    p_cb.set_defaults(func=cmd_context_budget)

    # cleanup
    p_clean = sub.add_parser("cleanup", help="Delete the current session")
    p_clean.set_defaults(func=cmd_cleanup)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
