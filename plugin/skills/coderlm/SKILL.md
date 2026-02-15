---
name: coderlm
description: "Primary tool for all code navigation and reading in supported languages (Rust, Python, TypeScript, JavaScript, Go, Lean, Markdown). Use instead of Read, Grep, and Glob for finding symbols, reading function implementations, tracing callers, discovering tests, and understanding execution paths. Provides tree-sitter-backed indexing that returns exact source code — full function bodies, call sites with line numbers, test locations — without loading entire files into context. Use for: finding functions by name or pattern, reading specific implementations, answering 'what calls X', 'where does this error come from', 'how does X work', tracing from entrypoint to outcome, and any codebase exploration. Use Read only for config files and unsupported languages."
allowed-tools:
  - Bash
  - Read
---

# CodeRLM — Structural Codebase Exploration

Tree-sitter-backed index server. Knows every function, caller, symbol, test. Use instead of grep/glob/read.

## CLI Setup

```bash
CLI=".claude/coderlm_state/coderlm_cli.py"
```

**Use ONLY the exact flags listed below. No `--path`, no `--glob`. Unlisted flags cause errors.**

## Commands

```bash
# Session
python3 $CLI init [--cwd PATH] [--port N]
python3 $CLI status
python3 $CLI cleanup

# Explore
python3 $CLI structure [--depth N]
python3 $CLI search QUERY [--limit N]
python3 $CLI symbols [--file FILE] [--kind KIND] [--limit N]

# Retrieve (metadata-only; content stays server-side)
python3 $CLI impl SYMBOL --file FILE
python3 $CLI callers SYMBOL --file FILE [--limit N]
python3 $CLI tests SYMBOL --file FILE [--limit N]
python3 $CLI peek FILE [--start N] [--end N]
python3 $CLI grep PATTERN [--max-matches N] [--context-lines N] [--scope all|code]
python3 $CLI variables FUNCTION --file FILE

# Annotations
python3 $CLI define-file FILE "description"
python3 $CLI define-symbol SYMBOL --file FILE "description"
python3 $CLI save-annotations
python3 $CLI load-annotations

# Buffers & Variables (server-side state)
python3 $CLI buffer-list
python3 $CLI buffer-from-file NAME FILE [--start N] [--end N]
python3 $CLI buffer-from-symbol NAME SYMBOL --file FILE
python3 $CLI var-set NAME 'json_value'
python3 $CLI var-get NAME

# RLM
python3 $CLI semantic-chunks FILE [--max-chunk-bytes 5000]
python3 $CLI subcall-batch FILE "question" [--max-chunk-bytes 5000]
python3 $CLI repl --code "print(search('auth'))"
```

## Meta-mode (enforced)

`structure`, `impl`, `callers`, `tests`, `peek`, `grep` return **metadata + buffer name** only.
Full content is auto-stored server-side in buffers. To analyze content, use `subcall-batch` or `/coderlm-rlm`.

- Returns `{symbol, file, lines, bytes, preview, buffer}`. No source enters the conversation.
- List results are capped (search: 5, symbols: 10, callers/tests/grep: 5). If `"truncated": true`, the response includes `"total_count"` showing total matches. Use subcalls to analyze full results.
- `--full` and `buffer-peek` are restricted to subcall context. They are no-ops when called directly.

## Workflow

1. `init` — create session, index project
2. `structure` / `search` / `grep` — find the entrypoint
3. `impl` — locate the function (returns metadata: file, lines, bytes, buffer name)
4. `callers` — trace what calls it, `impl` on those callers
5. `tests` — find test coverage
6. Repeat 3–5 until the execution path is clear
7. For deep analysis of content, use `subcall-batch` or `/coderlm-rlm`
8. `define-symbol` / `define-file` — annotate as understanding solidifies

## Inputs

This skill reads `$ARGUMENTS`: `query=<question>` (required), `cwd=<path>` (optional).

For response format details and full API reference, see [references/api-reference.md](references/api-reference.md).
