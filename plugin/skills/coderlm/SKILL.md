---
name: coderlm
description: "Recursive Language Model (RLM) for codebase exploration and deep analysis. Use for ALL code navigation in supported languages (Rust, Python, TypeScript, JavaScript, Go, Lean). Delegates exploration to haiku sub-LMs via deep-query — the root never runs REPL loops. Use Read only for config files, markdown, and unsupported languages."
allowed-tools:
  - Bash
  - Read
  - Task
---

# CodeRLM — Recursive Language Model

**When invoked, immediately begin executing. Do not summarize — start working.**

Parse `$ARGUMENTS` for: `query=<question>` (required), `target=<file_or_module>` (optional), `cwd=<path>` (optional), `max_chunk_bytes=<N>` (optional, default 5000).

```bash
CLI=".claude/coderlm_state/coderlm_cli.py"
```

## Setup

```bash
python3 $CLI init [--cwd PATH]
# Output includes Instance: <id> — save it for all subsequent commands
```

**Concurrent session isolation:** `init` generates a unique instance ID. Prefix **all** subsequent CLI calls with it so multiple Claude sessions in the same repo don't collide:

```bash
CODERLM_INSTANCE=<id> python3 $CLI deep-query "..."
CODERLM_INSTANCE=<id> python3 $CLI repl --code "..."
CODERLM_INSTANCE=<id> python3 $CLI subcall-batch FILE "..."
```

Recursive calls (deep-query → haiku → subcall-batch → llm_query) inherit the instance ID automatically through the environment.

## Exploration (multi-file)

Use `deep-query` for any question requiring codebase exploration. It spawns a haiku sub-LM that runs the full Algorithm 1 loop (scout, analyze, synthesize) and returns a structured result.

```bash
CODERLM_INSTANCE=<id> python3 $CLI deep-query "How does authentication work?"
# Returns: {"result": {"answer": "...", "evidence": [...], "files_analyzed": [...]}, "depth": 0}
```

The haiku sub-LM can itself call `subcall-batch`, `llm_query`, and even recursive `deep-query` for sub-problems. Recursion is gated by `CODERLM_MAX_DEPTH` (default 3).

## File Analysis (single file)

When you already know the file, use `subcall-batch` to analyze it directly:

```bash
CODERLM_INSTANCE=<id> python3 $CLI subcall-batch src/routes.rs "What auth checks exist?" [--max-chunk-bytes 5000]
# Returns: {"results": [...], "count": N}
```

## Quick Metadata (REPL, for pre-flight only)

Use the REPL for quick metadata lookups before deciding what to deep-query:

```bash
CODERLM_INSTANCE=<id> python3 $CLI repl --code "print(search('auth'))"
CODERLM_INSTANCE=<id> python3 $CLI repl --code "print(symbols(file='src/main.rs'))"
```

## Annotations (direct CLI)

```bash
CODERLM_INSTANCE=<id> python3 $CLI define-file FILE "description"
CODERLM_INSTANCE=<id> python3 $CLI save-annotations
CODERLM_INSTANCE=<id> python3 $CLI load-annotations
```

## Rules

- **Use `deep-query` for exploration.** Don't run REPL loops in the root context.
- **Use `subcall-batch` when you already know the file.**
- **REPL is for quick metadata only** — use it for pre-flight checks before deciding what to deep-query or subcall-batch.
- **Always prefix `CODERLM_INSTANCE=<id>`** on every CLI call (except `init`). This ensures concurrent sessions don't clobber each other's state.
- If `deep-query` returns a warning about no structured Final, the sub-LM may have failed — check the raw result or retry with a more specific query.
- Max recursion depth is 3 by default. Override with `--max-depth N`.
