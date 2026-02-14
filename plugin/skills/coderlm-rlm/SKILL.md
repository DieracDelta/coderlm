---
name: coderlm-rlm
description: "Run a Recursive Language Model (RLM) deep analysis loop over a codebase. Use when a question requires understanding large amounts of code — tracing complex call chains, auditing entire modules, or answering questions that span many files. Delegates chunk-level reasoning to a haiku subagent (llm_query) and synthesizes findings. Use /coderlm for quick lookups; use /coderlm-rlm for deep analysis."
allowed-tools:
  - Bash
  - Read
  - Task
---

# CodeRLM Deep Analysis (RLM Loop)

**When this skill is invoked, immediately begin executing the workflow below. Do not summarize these instructions — start working.**

Parse `$ARGUMENTS` for: `query=<question>` (required), `target=<file_or_module>` (optional), `max_chunk_bytes=<N>` (optional, default 5000). If no query is provided, ask the user what they want to analyze.

This skill implements the RLM paper's Algorithm 1: large context lives in server-side buffers, chunk-level reasoning is delegated to a sub-LM (Haiku), and you synthesize findings. Use `/coderlm` for quick single-symbol lookups; this skill is for deep multi-file analysis.

## CLI Setup

```bash
CLI=".claude/coderlm_state/coderlm_cli.py"
```

## Execute the RLM Loop

### Step 1: Initialize

```bash
python3 $CLI init
python3 $CLI var-set query '"<the user question>"'
python3 $CLI var-set status '"scouting"'
```

### Step 2: Scout

Get an overview of the target area. Identify relevant files and entry points.

```bash
python3 $CLI structure --depth 2
python3 $CLI search <key_terms>
python3 $CLI grep <patterns> --scope code
```

Store scouting results:
```bash
python3 $CLI repl --code "
results = search('<term>')
set_var('scout_results', [s['name'] + ' in ' + s['file'] for s in results])
"
```

### Step 3: Load Target as Buffers

For each file identified during scouting, load it as a buffer:

```bash
python3 $CLI buffer-from-file main_rs src/main.rs --start 0 --end 200
python3 $CLI buffer-from-symbol handler_fn handle_request --file src/routes.rs
```

### Step 4: Semantic Chunking

Split target files into symbol-aligned chunks:

```bash
python3 $CLI semantic-chunks src/routes.rs --max-chunk-bytes 5000
```

### Step 5: Subcall Loop (Delegate to Sub-LM)

For batch processing of an entire file:

```bash
python3 $CLI subcall-batch src/routes.rs "What authentication checks exist?" --max-chunk-bytes 5000
```

Or for targeted subcalls via the REPL:

```bash
python3 $CLI repl --code "
# Load specific chunk
load_buffer('chunk_auth', 'src/auth.rs', 0, 100)
content = peek('chunk_auth', 0, 5000)

# Delegate to sub-LM
result = llm_query(
    'What authentication methods are implemented here?',
    context=content,
    chunk_id='auth_module'
)
print(f'Findings: {len(result.get(\"findings\", []))}')
"
```

### Step 6: Collect and Review Findings

```bash
python3 $CLI subcall-results
python3 $CLI repl --code "
results = subcall_results()
for r in results:
    for f in r.get('findings', []):
        add_finding(f'{f[\"point\"]} ({f[\"confidence\"]})')
print(get_var('findings'))
"
```

### Step 7: Synthesize

Combine findings into a coherent answer. If more investigation is needed, go back to Step 2 with refined queries (using `suggested_queries` from subcall results).

```bash
python3 $CLI repl --code "
findings = get_var('findings')
# Build synthesis from findings...
set_final({
    'answer': 'The authentication system uses...',
    'evidence': findings,
    'files_analyzed': ['src/auth.rs', 'src/routes.rs']
})
"
```

### Step 8: Check Termination

```bash
python3 $CLI check-final
```

If `is_set: true`, the analysis is complete. Present the `value` to the user.
If `is_set: false`, refine the query and loop back to Step 2.

## Orchestration Rules

1. **Keep context small.** Never paste large buffers into the main conversation. Use `buffer-peek` for small slices, `llm_query` for chunk analysis.
2. **Use metadata.** `buffer-list` and `var-list` return summaries, not content. Plan from metadata.
3. **Batch when possible.** `subcall-batch` is better than individual `llm_query` calls for file-wide analysis.
4. **Track progress.** Use `var-set status` to mark where you are in the loop.
5. **Accumulate findings.** Use `add_finding()` in the REPL to build up evidence incrementally.
6. **Follow suggested queries.** Subcall results include `suggested_queries` — use these to guide the next iteration.

## Error Recovery

- If a subcall fails, skip it and continue with the next chunk
- If the server disconnects, re-run `init` (buffers and variables are session-scoped)
- If the REPL errors, check `stderr` in the exec output
- Set a maximum of 3 loop iterations before synthesizing with available findings
