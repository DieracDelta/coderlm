---
name: coderlm-rlm
description: "Run a Recursive Language Model (RLM) deep analysis loop over a codebase. Use when a question requires understanding large amounts of code — tracing complex call chains, auditing entire modules, or answering questions that span many files. Delegates chunk-level reasoning to a haiku subagent (llm_query) and synthesizes findings. Use /coderlm for quick lookups; use /coderlm-rlm for deep analysis."
allowed-tools:
  - Bash
  - Read
  - Task
---

# CodeRLM Deep Analysis (RLM Loop)

**When invoked, immediately begin executing. Do not summarize — start working.**

Parse `$ARGUMENTS` for: `query=<question>` (required), `target=<file_or_module>` (optional), `max_chunk_bytes=<N>` (optional, default 5000).

```bash
CLI=".claude/coderlm_state/coderlm_cli.py"
```

## Step 1: Initialize

```bash
python3 $CLI init
python3 $CLI var-set query '"<the user question>"'
python3 $CLI var-set status '"scouting"'
```

## Step 2: Scout

All commands return metadata-only — no source enters the conversation.

```bash
python3 $CLI structure --depth 2   # meta-only: {file_count, language_breakdown, buffer}
python3 $CLI search <key_terms>
python3 $CLI grep <patterns> --scope code
python3 $CLI impl <symbol> --file <file>
# impl returns: {symbol, file, lines, bytes, preview, buffer: "impl::file::symbol"}
```

## Step 3: Load Buffers

Buffers are auto-created by `impl`, `callers`, `tests`, `peek`, `grep`.
For additional content:

```bash
python3 $CLI buffer-from-file main_rs src/main.rs --start 0 --end 200
python3 $CLI buffer-from-symbol handler_fn handle_request --file src/routes.rs
```

## Step 4: Semantic Chunking

```bash
python3 $CLI semantic-chunks src/routes.rs --max-chunk-bytes 5000
```

## Step 5: Subcall Loop

Batch (preferred for file-wide analysis):
```bash
python3 $CLI subcall-batch src/routes.rs "What auth checks exist?" --max-chunk-bytes 5000
```

Targeted (using auto-created buffers):
```bash
python3 $CLI repl --code "
content = peek('impl::src/auth.rs::authenticate', 0, 5000)
result = llm_query('What auth methods?', context=content, chunk_id='auth')
"
```

## Step 6: Collect Findings

```bash
python3 $CLI repl --code "
results = subcall_results()
for r in results:
    for f in r.get('findings', []):
        add_finding(f'{f[\"point\"]} ({f[\"confidence\"]})')
print(get_var('findings'))
"
```

## Step 7: Synthesize

```bash
python3 $CLI repl --code "
set_final({'answer': '...', 'evidence': get_var('findings'), 'files_analyzed': [...]})
"
```

Check: `python3 $CLI check-final`. If `is_set: true`, present to user. Otherwise loop to Step 2.

## Rules

- **NEVER read source content into the conversation.** No `buffer-peek`, no `peek --full`, no `impl --full`, no `Read` on source files. Every byte of content in the conversation persists in history and compounds token cost on every subsequent turn.
- **ALL content analysis goes through subagents.** Use `subcall-batch` (preferred for file-wide analysis) or `llm_query` (for targeted chunks). Subagents read content server-side via haiku — the root LLM never sees the source.
- Scout commands (`structure`, `search`, `grep`, `symbols`, `impl`, `peek`, `callers`, `tests`) return metadata only (names, line numbers, byte sizes, buffer references). Use them freely for navigation. List results are capped (search: 5, symbols: 10, callers/tests/grep: 5) — check `"truncated"` and `"total_count"` fields.
- Subcalls can recurse up to `CODERLM_MAX_DEPTH` (default 3). If a subcall needs to understand code outside its chunk, it will automatically spawn deeper subcalls. Set the `CODERLM_MAX_DEPTH` env var to control recursion depth.
- Prefer `subcall-batch` over individual `llm_query` — it handles chunking and parallelism automatically.
- Max 3 loop iterations before synthesizing with available findings.
- If subcall fails, skip and continue. If server disconnects, re-run `init`.
