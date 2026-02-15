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

## Algorithm 1: Recursive Language Model

All interaction goes through the REPL. You write Python code, see only metadata (stdout_lines, stdout_preview, stdout_size). No coderlm output enters the conversation directly. Content analysis is delegated to haiku via `llm_query()`.

## Step 1: Initialize

```bash
python3 $CLI init
python3 $CLI repl --code "
set_var('query', '<the user question>')
set_var('status', 'scouting')
"
```

## Step 2: Scout (via REPL)

```bash
python3 $CLI repl --code "
results = search('<key_terms>')
print(f'Found {len(results)} symbols')
for r in results[:10]:
    print(f'  {r[\"name\"]} in {r[\"file\"]} ({r[\"kind\"]})')
"

python3 $CLI repl --code "
matches = grep('<pattern>', scope='code')
print(f'{len(matches)} matches')
for m in matches[:10]:
    print(f'  {m[\"file\"]}:{m[\"line\"]}')
"
```

## Step 3: Analyze (delegate to sub-LM)

Batch (preferred for file-wide analysis):
```bash
python3 $CLI subcall-batch src/routes.rs "What auth checks exist?" --max-chunk-bytes 5000
```

Targeted (using REPL + llm_query):
```bash
python3 $CLI repl --code "
source = impl_('authenticate', 'src/auth.rs')
result = llm_query('What auth methods does this use?', context=source, chunk_id='auth')
print(f'Findings: {len(result.get(\"findings\", []))}')
for f in result.get('findings', []):
    print(f'  [{f[\"confidence\"]}] {f[\"point\"]}')
"
```

## Step 4: Collect Findings

```bash
python3 $CLI repl --code "
results = subcall_results()
for r in results:
    for f in r.get('findings', []):
        add_finding(f'{f[\"point\"]} ({f[\"confidence\"]})')
findings = get_var('findings')
print(f'{len(findings)} findings collected')
for f in findings[:5]:
    print(f'  - {f}')
"
```

## Step 5: Synthesize

```bash
python3 $CLI repl --code "
set_final({'answer': '...', 'evidence': get_var('findings'), 'files_analyzed': [...]})
"
```

Check: `python3 $CLI check-final`. If `is_set: true`, present to user. Otherwise loop to Step 2.

## Rules

- **ALL coderlm interaction goes through the REPL.** Never call index commands (search, impl, callers, grep, etc.) as direct CLI commands — they are blocked outside REPL/subcall context.
- **The REPL returns metadata only.** You see `{stdout_lines, stdout_preview (200 chars), stdout_size}`. No full output enters the conversation. Write Python code that prints what you need to see.
- **Content analysis goes through sub-LMs.** Use `llm_query()` or `subcall-batch` — haiku reads content server-side, you see only structured findings.
- Subcalls can recurse up to `CODERLM_MAX_DEPTH` (default 3). Sub-LMs can spawn their own subcalls for cross-module dependencies.
- Prefer `subcall-batch` over individual `llm_query` for file-wide analysis.
- Max 3 loop iterations before synthesizing with available findings.
- If subcall fails, skip and continue. If server disconnects, re-run `init`.
