---
name: coderlm
description: "Recursive Language Model (RLM) for codebase exploration and deep analysis. Use for ALL code navigation in supported languages (Rust, Python, TypeScript, JavaScript, Go, Lean) and indexed PDFs. Delegates exploration to codex sub-LMs via deep-query (codex-nix) — the root never runs REPL loops. Use Read only for config files, markdown, and unsupported languages."
allowed-tools:
  - Bash
  - Read
  - Task
---

# CodeRLM — Recursive Language Model

**When invoked, immediately begin executing. Do not summarize — start working.**

Parse `$ARGUMENTS` for: `query=<question>` (required), `target=<file_or_module>` (optional), `cwd=<path>` (optional), `max_chunk_bytes=<N>` (optional, default 5000).

```bash
CLI=".coderlm/codex_state/coderlm_cli.py"
```

## Setup

```bash
python3 $CLI init [--cwd PATH]
```

## Exploration (multi-file)

Use `deep-query` for any question requiring codebase exploration. It spawns a codex sub-LM via codex-nix that runs the full Algorithm 1 loop (scout, analyze, synthesize) and returns a structured result.

```bash
python3 $CLI deep-query "How does authentication work?"
# Returns: {"result": {"answer": "...", "evidence": [...], "files_analyzed": [...]}, "depth": 0}
```

The codex sub-LM can itself call `subcall-batch`, `llm_query`, and even recursive `deep-query` for sub-problems. Recursion is gated by `CODERLM_MAX_DEPTH` (default 2).

## File Analysis (single file)

When you already know the file, use `subcall-batch` to analyze it directly:

```bash
python3 $CLI subcall-batch src/routes.rs "What auth checks exist?" [--max-chunk-bytes 5000]
# Returns: {"results": [...], "count": N}
```

## Quick Metadata (REPL, for pre-flight only)

Use the REPL for quick metadata lookups before deciding what to deep-query:

```bash
python3 $CLI repl --code "print(search('auth'))"
python3 $CLI repl --code "print(symbols(file='src/main.rs'))"
python3 $CLI repl --code "print(grep('pattern', scope='code'))"
```

## Annotations (direct CLI)

```bash
python3 $CLI define-file FILE "description"
python3 $CLI define-symbol SYMBOL --file FILE "description"
python3 $CLI save-annotations
python3 $CLI load-annotations
```

## Rules

- **Use `deep-query` for exploration.** Don't run REPL loops or direct index commands (structure, symbols, grep, impl, callers, etc.) in the root context. Those are REPL-restricted.
- **Use `subcall-batch` when you already know the file.**
- **REPL is for quick metadata only** — use it for pre-flight checks before deciding what to deep-query or subcall-batch.
- If `deep-query` returns `status: \"final_missing\"` or `status: \"subcall_failed\"`, the sub-LM failed — inspect previews and retry with a narrower query.
- Max recursion depth is 2 by default. Override with `--max-depth N`.
- Multiple Claude sessions in the same project are automatically isolated via PID-keyed instance files.
