# AI usage log

Raw notes for `AI_USAGE.md`. Real events only. One entry per event.

| Date | Task | Type (helped / had to fix / struggled) | What happened | Fix / outcome |
|---|---|---|---|---|
| 2026-11-10 | Setup | helped | Claude Code adapted the spec-driven-dev skill to this assignment (6 stages, AI usage log, submission checklist) | Reviewed by the user, who changed the stage approvals and naming |
| 2026-11-10 | Stage 2 | had to fix | Claude's first architecture draft left the timeout mechanism unspecified (the common `with ThreadPoolExecutor` pattern would silently defeat it), unsafe DB writes from threads, SQLite cascades that silently don't work (foreign keys off), and a Docker volume the non-root user couldn't write. Caught by an independent reviewer agent, not by the author | All 19 review findings applied in architecture v2 |
| 2026-11-10 | Stage 2 | helped | Claude checked the current Claude API docs and caught API rules that affect the design: forced tool_choice is rejected (400), all parallel tool results must go in one message, the history-editing check on replayed thinking blocks | Built into D1, D2, D5 |
