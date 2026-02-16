---
name: coderlm
description: Explore a codebase using tree-sitter-backed indexing. Use when you need to understand how code works, trace execution paths, find where errors originate, or understand the sequence of events that produce a particular outcome. Prefer this over grep/glob/read for structural code questions.
---

# CodeRLM — Structural Codebase Exploration

You have access to a tree-sitter-backed index server that knows the structure of this codebase: every function, every caller, every symbol. Use it instead of guessing with grep.

## Setup

```bash
CLI=".gemini/coderlm_state/coderlm_cli.py"
python3 $CLI init
```

## Tools

**Use ONLY the exact flags shown. There is no `--path` flag, no `--glob` flag.**

```bash
CLI=".gemini/coderlm_state/coderlm_cli.py"

python3 $CLI structure [--depth N]                                      # File tree (always full tree, no path filter)
python3 $CLI search QUERY [--limit N]                                   # Find symbols by name
python3 $CLI symbols [--file FILE] [--kind KIND] [--limit N]            # List symbols, optionally filter by file
python3 $CLI impl SYMBOL --file FILE                                    # Get exact implementation (--file required)
python3 $CLI callers SYMBOL --file FILE [--limit N]                     # Who calls this? (--file required)
python3 $CLI tests SYMBOL --file FILE [--limit N]                       # Tests for this symbol (--file required)
python3 $CLI variables FUNCTION --file FILE                             # Local variables (--file required)
python3 $CLI peek FILE [--start N] [--end N]                            # Read a specific line range
python3 $CLI grep PATTERN [--max-matches N] [--context-lines N] [--scope all|code]  # Regex search (all files, no file filter)
```

## How to Explore

Do not scan files looking for relevant code. Instead, work the way a human engineer traces through a codebase:

**Start from an entrypoint.** Every exploration begins somewhere concrete — an error message, a function name, an API endpoint, a log line. Use `grep` or `search` to locate that entrypoint in the index.

**Trace the path.** Once you've found the entrypoint, use `callers` to understand what invokes it and `impl` to read what it does. Follow the chain: what calls this? What does that caller do? Build a mental model of the execution path, not a list of files.

**Understand the sequence of events.** The goal is to reconstruct the causal chain: what had to happen in order to produce the state you're looking at. This means tracing upstream (what called this, and with what arguments?) and sometimes downstream (what happens after this point, and does it matter?).

**Stop when you have the narrative.** You're done exploring when you can explain the path from trigger to outcome — not when you've read every related file.
