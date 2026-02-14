---
name: coderlm
description: "Primary tool for all code navigation and reading in supported languages (Rust, Python, TypeScript, JavaScript, Go). Use instead of Read, Grep, and Glob for finding symbols, reading function implementations, tracing callers, discovering tests, and understanding execution paths. Provides tree-sitter-backed indexing that returns exact source code — full function bodies, call sites with line numbers, test locations — without loading entire files into context. Use for: finding functions by name or pattern, reading specific implementations, answering 'what calls X', 'where does this error come from', 'how does X work', tracing from entrypoint to outcome, and any codebase exploration. Use Read only for config files, markdown, and unsupported languages."
allowed-tools:
  - Bash
  - Read
---

# CodeRLM — Structural Codebase Exploration

You have access to a tree-sitter-backed index server that knows the structure of this codebase: every function, every caller, every symbol, every test reference. Use it instead of guessing with grep.

The tree-sitter is monitoring the directory and will stay up-to-date as you make changes in the codebase.

## How to Explore

Do not scan files looking for relevant code. Work the way an engineer traces through a codebase:

**Start from an entrypoint.** Every exploration begins somewhere concrete — an error message, a function name, an API endpoint, a log line. Use `search` or `grep` to locate that entrypoint in the index.

**Trace the path.** Once you've found an entrypoint, use `callers` to understand what invokes it and `impl` to read what it does. Follow the chain: what calls this? What does that caller do? What state does it pass in? Build a model of the execution path, not a list of files.

**Understand the sequence of events.** The goal is to reconstruct the causal chain — what had to happen to produce the state you're looking at. Trace upstream (what called this, with what arguments?) and sometimes downstream (what happens after, does it matter?).

**Stop when you have the narrative.** You're done exploring when you can explain the path from trigger to outcome — not when you've read every related file.

## What This Replaces

Without the index, you explore by globbing for filenames, grepping for strings, and reading entire files hoping to find relevant sections. That works, but it's wasteful and produces false confidence — you see code near your search term but miss the actual execution path.

With the index:
- **Symbol search** instead of string matching — find the function, not every comment mentioning it
- **Caller chains** instead of grep-and-hope — know exactly what invokes a function
- **Exact implementations** instead of full-file reads — get the 20-line function body, not the 500-line file
- **Test discovery** by symbol reference — find what tests cover a function, not by guessing test filenames

## Prerequisites

The `coderlm-server` must be running. Start it separately:

```bash
coderlm-server serve                     # indexes projects on-demand
coderlm-server serve /path/to/project    # pre-index a specific project
```

If the server is not running, all CLI commands will fail with a connection error.

## CLI Reference

The CLI is available via a symlink created at session start:

```bash
CLI=".claude/coderlm_state/coderlm_cli.py"
```

This symlink is set up automatically by the SessionStart hook. If it doesn't exist, the coderlm plugin may not be installed or the session hasn't started properly.

**IMPORTANT — use ONLY the exact flags listed below. There is no `--path` flag, no `--glob` flag, and no `--file` flag on commands that don't list it. Using unlisted flags will cause an error.**

### Complete command reference

```bash
# Session management
python3 $CLI init [--cwd PATH] [--port N]
python3 $CLI status
python3 $CLI cleanup

# Project overview (no file/path filter — always shows full tree)
python3 $CLI structure [--depth N]

# Find symbols by name (searches the whole index, not filterable by file)
python3 $CLI search QUERY [--limit N]

# List symbols in a specific file or by kind
python3 $CLI symbols [--file FILE] [--kind KIND] [--limit N]

# Get the full source of a specific symbol (--file is REQUIRED)
python3 $CLI impl SYMBOL --file FILE

# Find all call sites for a symbol (--file is REQUIRED)
python3 $CLI callers SYMBOL --file FILE [--limit N]

# Find tests referencing a symbol (--file is REQUIRED)
python3 $CLI tests SYMBOL --file FILE [--limit N]

# List local variables inside a function (--file is REQUIRED)
python3 $CLI variables FUNCTION --file FILE

# Read a specific line range from a file
python3 $CLI peek FILE [--start N] [--end N]

# Regex search across ALL indexed files (no file/path/glob filter)
python3 $CLI grep PATTERN [--max-matches N] [--context-lines N] [--scope all|code]

# Annotations
python3 $CLI define-file FILE "description"
python3 $CLI redefine-file FILE "description"
python3 $CLI define-symbol SYMBOL --file FILE "description"
python3 $CLI redefine-symbol SYMBOL --file FILE "description"
python3 $CLI mark FILE TYPE
python3 $CLI save-annotations
python3 $CLI load-annotations

# RLM: Buffers (server-side, metadata-only responses)
python3 $CLI buffer-list
python3 $CLI buffer-create NAME "content" [--description "..."]
python3 $CLI buffer-from-file NAME FILE [--start N] [--end N]
python3 $CLI buffer-from-symbol NAME SYMBOL --file FILE
python3 $CLI buffer-info NAME
python3 $CLI buffer-peek NAME [--start N] [--end N]
python3 $CLI buffer-delete NAME

# RLM: Variables (server-side key-value store)
python3 $CLI var-list
python3 $CLI var-set NAME 'json_value'
python3 $CLI var-get NAME
python3 $CLI var-delete NAME
python3 $CLI check-final

# RLM: Semantic chunks (symbol-aligned chunking)
python3 $CLI semantic-chunks FILE [--max-chunk-bytes 5000]

# RLM: Sub-LM dispatch
python3 $CLI subcall-results
python3 $CLI clear-subcall-results
python3 $CLI subcall-batch FILE "question" [--max-chunk-bytes 5000]

# RLM: REPL (execute Python with injected coderlm helpers)
python3 $CLI repl --code "print(search('auth'))"
```

**Prefer `impl` and `peek` over the Read tool.** They return exactly the code you need — a single function from a 1000-line file, a specific line range — without loading irrelevant code into context. Fall back to Read only when you need an entire small file.

## Inputs

This skill reads `$ARGUMENTS`. Accepted patterns:
- `query=<question>` (required): what to find or understand
- `cwd=<path>` (optional): project directory, defaults to cwd
- `port=<N>` (optional): server port, defaults to 3000

If no query is provided, ask what the user wants to find or understand about the codebase.

## Workflow

1. **Init** — `cli init` to create a session and index the project.
2. **Orient** — `cli structure` to see the project layout. Identify likely starting points.
3. **Find the entrypoint** — `cli search` or `cli grep` to locate the starting symbol or pattern.
4. **Retrieve** — `cli impl` to read the exact implementation. Not the file. The function.
5. **Trace** — `cli callers` to see what calls it. `cli impl` on those callers. Follow the chain.
6. **Widen** — `cli tests` to find test coverage. `cli grep` for related patterns discovered during tracing.
7. **Annotate** — `cli define-symbol` and `cli define-file` as understanding solidifies.
8. **Synthesize** — Compile findings into a coherent answer with specific file:line references.

Steps 3–7 repeat. A typical exploration is: find a symbol → read its implementation → trace its callers → read those implementations → discover related symbols → repeat until the causal chain is clear.

## When to Use the Server vs Native Tools

| Task | Use server | Why |
|------|-----------|-----|
| Find a function by name | `search` | Index lookup, not file globbing |
| Find code when name is unknown | `grep` + `symbols` | Searches all indexed files at once |
| Get a function's source | `impl` | Returns just that function, even from large files |
| Read specific lines | `peek` | Surgical extraction, not the whole file |
| Find what calls a function | `callers` | Cross-project search with exact call sites |
| Find tests for a function | `tests` | By symbol reference, not filename guessing |
| Get project overview | `structure` | Tree with file counts and language breakdown |
| Read an entire small file | Read tool | When you genuinely need the whole file |

**Default to the server.** Use Read only when you need an entire file or the server is unavailable.

## Troubleshooting

- **"Cannot connect to coderlm-server"** — Server not running. Start with `coderlm-server serve`.
- **"No active session"** — Run `cli init` first.
- **"Project was evicted"** — Server hit capacity (default 5 projects). Re-run `cli init`.
- **Search returns nothing relevant** — Try broader grep patterns or list all symbols: `cli symbols --limit 200`.

For the full API endpoint reference, see [references/api-reference.md](references/api-reference.md).