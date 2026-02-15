---
name: coderlm
description: "Primary tool for all code navigation and reading in supported languages (Rust, Python, TypeScript, JavaScript, Go, Lean, Markdown). Use instead of Read, Grep, and Glob for finding symbols, reading function implementations, tracing callers, discovering tests, and understanding execution paths. All interaction goes through the REPL — you write Python code, see only metadata about results. Use Read only for config files and unsupported languages."
allowed-tools:
  - Bash
  - Read
---

# CodeRLM — Structural Codebase Exploration

Tree-sitter-backed index server. All queries go through the REPL — you write Python code, see metadata-only responses. No coderlm output enters the conversation directly.

## CLI Setup

```bash
CLI=".claude/coderlm_state/coderlm_cli.py"
```

## Session Management (direct CLI)

```bash
python3 $CLI init [--cwd PATH] [--port N]
python3 $CLI status
python3 $CLI cleanup
python3 $CLI check-final
```

## REPL (all exploration goes here)

All index queries (search, symbols, impl, callers, tests, peek, grep) are REPL-only. The REPL captures stdout and returns metadata: `{stdout_lines, stdout_preview (200 chars), stdout_size}`. Full output stays server-side.

```bash
# Navigate
python3 $CLI repl --code "
results = search('authenticate')
print(f'Found {len(results)} symbols')
for r in results[:5]:
    print(f'  {r[\"name\"]} in {r[\"file\"]} ({r[\"kind\"]})')
"

# Read implementations
python3 $CLI repl --code "
source = impl_('handle_request', 'src/routes.rs')
print(f'Source: {len(source)} chars')
"

# Trace callers
python3 $CLI repl --code "
c = callers('authenticate', 'src/auth.rs')
print(f'{len(c)} callers')
for call in c[:5]:
    print(f'  {call[\"file\"]}:{call[\"line\"]}')
"

# Grep
python3 $CLI repl --code "
matches = grep('TODO|FIXME', scope='code')
print(f'{len(matches)} matches')
"

# Delegate content analysis to haiku sub-LM
python3 $CLI repl --code "
result = llm_query('What auth checks exist?', context=impl_('authenticate', 'src/auth.rs'), chunk_id='auth')
print(json.dumps(result, indent=2))
"
```

### Available REPL functions

**Index queries:** `search(q)`, `symbols(file, kind, limit)`, `impl_(symbol, file)`, `callers(symbol, file)`, `tests(symbol, file)`, `grep(pattern, scope)`, `peek_file(file, start, end)`

**Buffers:** `load_buffer(name, file, start, end)`, `load_symbol(name, symbol, file)`, `create_buffer(name, content)`, `peek(buffer_name, start, end)`, `list_buffers()`, `delete_buffer(name)`

**Variables:** `set_var(name, value)`, `get_var(name)`, `list_vars()`

**RLM:** `llm_query(prompt, context, chunk_id)`, `subcall_results()`, `clear_subcall_results()`, `set_final(result)`, `add_finding(text)`

**Persistence:** `last_output()`, `save_result(name, value)`, `get_result(name)`

## Batch Analysis (direct CLI)

For file-wide analysis, `subcall-batch` is a convenience wrapper:

```bash
python3 $CLI subcall-batch src/routes.rs "What auth checks exist?" [--max-chunk-bytes 5000]
```

## Annotations (direct CLI)

```bash
python3 $CLI define-file FILE "description"
python3 $CLI define-symbol SYMBOL --file FILE "description"
python3 $CLI save-annotations
python3 $CLI load-annotations
```

## Workflow

1. `init` — create session, index project
2. REPL: `search()` / `grep()` — find entrypoints (see metadata preview only)
3. REPL: `impl_()` / `callers()` — navigate the call graph
4. REPL: `llm_query()` — delegate content understanding to haiku
5. REPL: `set_final()` — store conclusion
6. For deep multi-file analysis, use `/coderlm-rlm`

## Inputs

This skill reads `$ARGUMENTS`: `query=<question>` (required), `cwd=<path>` (optional).
