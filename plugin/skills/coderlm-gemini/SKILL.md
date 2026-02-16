---
name: coderlm
description: "Recursive Language Model (RLM) for codebase exploration and deep analysis. Use for ALL code navigation in supported languages (Rust, Python, TypeScript, JavaScript, Go, Lean) and indexed PDFs. Delegates exploration to gemini sub-LMs via deep-query — the root never runs REPL loops. Use read_file ONLY for config files, markdown, and unsupported languages."
allowed-tools:
  - run_shell_command
  - read_file
---

# CodeRLM — Recursive Language Model

**When invoked, immediately begin executing. Do not summarize — start working.**

Parse `$ARGUMENTS` for: `query=<question>` (required), `target=<file_or_module>` (optional), `cwd=<path>` (optional), `max_chunk_bytes=<N>` (optional, default 5000).

```bash
CLI=".gemini/coderlm_state/coderlm_cli.py"
```

## Setup

Ensure the coderlm-server is running. Then initialize the session:

```bash
python3 .gemini/coderlm_state/coderlm_cli.py init [--cwd PATH]
```

## Exploration (multi-file)

Use `deep-query` for any question requiring codebase exploration. It spawns a gemini sub-LM that runs the full Algorithm 1 loop (scout, analyze, synthesize) and returns a structured result.

```bash
python3 .gemini/coderlm_state/coderlm_cli.py deep-query "How does authentication work?"
# Returns: {"result": {"answer": "...", "evidence": [...], "files_analyzed": [...]}, "depth": 0}
```

The gemini sub-LM can itself call `subcall-batch`, `llm_query`, and even recursive `deep-query` for sub-problems. Recursion is gated by `CODERLM_MAX_DEPTH` (default 3).

## File Analysis (single file)

When you already know the file, use `subcall-batch` to analyze it directly:

```bash
python3 .gemini/coderlm_state/coderlm_cli.py subcall-batch src/routes.rs "What auth checks exist?" [--max-chunk-bytes 5000]
# Returns: {"results": [...], "count": N}
```

## Quick Metadata (REPL, for pre-flight only)

Use the REPL for quick metadata lookups before deciding what to deep-query:

```bash
python3 .gemini/coderlm_state/coderlm_cli.py repl --code "print(search('auth'))"
python3 .gemini/coderlm_state/coderlm_cli.py repl --code "print(symbols(file='src/main.rs'))"
python3 .gemini/coderlm_state/coderlm_cli.py repl --code "print(grep('pattern', scope='code'))"
```

## Annotations (direct CLI)

```bash
python3 .gemini/coderlm_state/coderlm_cli.py define-file FILE "description"
python3 .gemini/coderlm_state/coderlm_cli.py define-symbol SYMBOL --file FILE "description"
python3 .gemini/coderlm_state/coderlm_cli.py save-annotations
python3 .gemini/coderlm_state/coderlm_cli.py load-annotations
```

## Rules

- **Use `deep-query` for exploration.** Don't run REPL loops or direct index commands (structure, symbols, grep, impl, callers, etc.) in the root context. Those are REPL-restricted.
- **Use `subcall-batch` when you already know the file.**
- **REPL is for quick metadata only** — use it for pre-flight checks before deciding what to deep-query or subcall-batch.
- If `deep-query` returns a warning about no structured Final, the sub-LM may have failed — check the raw result or retry with a more specific query.
- Max recursion depth is 3 by default. Override with `--max-depth N`.
- Multiple Gemini sessions in the same project are automatically isolated via PID-keyed instance files.
