# Architecture Notes

## Deviations from the RLM Paper (Algorithm 1)

CodeRLM implements the Recursive Language Model pattern from the paper but adapts it for Claude Code's agentic environment. These are intentional design choices, not bugs.

| # | Paper says | We do | Why |
|---|-----------|-------|-----|
| D1 | Only constant-size metadata of stdout appended to hist | Full stdout returned to root LLM via REPL exec | Claude Code's agentic loop IS the history — we can't control what it puts in context. Server-side history is metadata-only (200-char preview). |
| D2 | Sub-LM invokes full model M | Sub-LM uses Haiku (2 tiers below root) | Cost/speed tradeoff. Paper also used GPT-5-mini under GPT-5. |
| D3 | REPL state persists ALL variables across iterations | Only server-side buffers/vars persist; Python namespace is ephemeral | Durable state on Rust server, not pickle-based. Must use `set_var()`/`get_var()` explicitly. |
| D4 | Automatic `while True` loop with Final check | No automatic loop; relies on Claude Code's agentic behavior | Platform constraint — Claude Code IS the loop. `check-final` exists for explicit termination. |
| D5 | History compaction is LLM-based semantic summarization | Compaction is syntactic dedup (consecutive same-path entries) | Good enough for API call history. Claude Code has its own context compaction. |
| D6 | Prompt P loaded as REPL variable | Codebase accessed via structured API (symbols, callers, grep) | Indexed access beats string manipulation for code. |
| D7 | Character-based chunking, LLM chooses decomposition | Symbol-aligned semantic chunking (tree-sitter) | Strictly better for code — chunks respect function boundaries. |
