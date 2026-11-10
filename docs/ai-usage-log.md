# AI usage log

Raw notes for `AI_USAGE.md`. Real events only. One entry per event.

| Date | Task | Type (helped / had to fix / struggled) | What happened | Fix / outcome |
|---|---|---|---|---|
| 2026-11-10 | Setup | helped | Claude Code adapted the spec-driven-dev skill to this assignment (6 stages, AI usage log, submission checklist) | Reviewed by the user, who changed the stage approvals and naming |
| 2026-11-10 | Stage 2 | had to fix | Claude's first architecture draft left the timeout mechanism unspecified (the common `with ThreadPoolExecutor` pattern would silently defeat it), unsafe DB writes from threads, SQLite cascades that silently don't work (foreign keys off), and a Docker volume the non-root user couldn't write. Caught by an independent reviewer agent, not by the author | All 19 review findings applied in architecture v2 |
| 2026-11-10 | Stage 2 | helped | Claude checked the current Claude API docs and caught API rules that affect the design: forced tool_choice is rejected (400), all parallel tool results must go in one message, the history-editing check on replayed thinking blocks | Built into D1, D2, D5 |
| 2026-11-10 | Stage 3 | had to fix | Claude's spec draft missed calculator holes: `1e999` / `1e308*10` produce infinity (the JSON response would crash with a 500) and `((2**1000)**1000)**1000` passes the exponent limit while building a ~125 MB integer. Also a slow-query test that could never fail and a "last month" test that would break with the real date. Caught by an independent reviewer agent that ran the values in Python | Spec v0.2: float-only math with finite checks, new ACs, fixed test designs |
| 2026-11-10 | T-1 | had to fix | Claude's first test fixture blocked all socket connections to keep tests offline, which also broke the local 127.0.0.1 socket pair that Python's asyncio event loop uses on Windows, so every test errored at startup | Allow only loopback addresses; AC-47 still proves internet access is blocked |
| 2026-11-10 | T-2 | helped | Claude wrote the data model, conversation service and routes test-first; all 11 tests passed on the first green run. A mutation check (deliberately breaking the tool-execution cascade) made AC-6 and AC-7 fail, which proves those tests really test the cascade | Mutation reverted; suite green |
| 2026-11-10 | T-3 | struggled | During the mutation check, Claude's `sed`/inline-Python edits silently didn't apply (shell escaping of `
`), so two tests looked like they couldn't catch a bug. Claude noticed the edits had not matched instead of trusting the green run | Redid the mutation with an exact file edit: AC-2 and AC-3 fail as they should |
| 2026-11-10 | T-3 | struggled | Mutation check: removing the final `last_message_at` update is not caught by AC-9, because the pending assistant message already sets it (and AC-9 only asks for ≥) | Kept the update (architecture §4 step 6); noted the limit of AC-9 |
| 2026-11-10 | T-3 | helped | Running the real container (not only the tests) showed that with no API key the SDK raises `TypeError`, not `anthropic.APIError`: HTTP 500 and a message stuck in `pending`. FR-25 didn't cover it | Raised as Q5 (spec change proposal for T-12) |
