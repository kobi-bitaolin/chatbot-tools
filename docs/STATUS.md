# Project status: chatbot-tools

- **Spec:** `docs/chatbot-spec.md` (v0.10, Approved, 2026-11-10)
- **Source:** `chatbot-tool.md` (S1)
- **Conventions (Git, agreed 2026-11-10):**
  - `main` always works; only tested work is merged into it.
  - One short-lived branch per feature (`feat/basic-chat`, `feat/calculator`, ...), merged into `main` when all tests pass, then deleted.
  - One commit per task, Conventional Commits with IDs, e.g. `feat(calculator): safe expression parser (FR-5, AC-7)`. Prefixes: feat, fix, test, docs, chore.
  - `docs/` is committed. `chatbot-tool.md`, `.env`, and DB files are git-ignored.
  - Remote: private repo https://github.com/kobi-bitaolin/chatbot-tools (created 2026-11-10).
  - **Standing yes (2026-11-10):** push `main` to `origin` after every merged task. Anything else (other branches, force-push, changing visibility, adding collaborators) needs a fresh yes. Make it public / share only at stage 6 with a fresh yes.
  - **Merges need a yes per task** (2026-11-10: the user declined a standing yes for merge + branch delete).
  - **Scope (2026-11-10):** build strictly what S1 asks, nothing else. `Message.status` kept (user's choice) as the way to handle failed turns (S1:328).
- **Current stage:** 4b, TDD implementation, T-1..T-11 done and merged; next T-12
- **Last updated:** 2026-11-10

## Next action
Stages 1-3 and the task list approved 2026-11-10. T-1..T-6 done and merged (T-6 merged 2026-11-10, incl. the v0.6 scope cuts; FR-26 kept in full after the scope review). T-7 (tool loop + neutral `LLMResult`) merged 2026-11-10, all 65 tests green, mutation-checked. Milestone 2 reached. **Provider change (2026-11-10):** the user switched the LLM to Google Gemini; **spec v0.7 approved 2026-11-10** (D9, FR-37, AC-62/63, task T-7b). Real Gemini checked with a scratchpad probe (key in `.env`): single tool, two tools in one round, no tools, tool error all work. Risk R1 fixed in v0.7 (calculator description + D0 wording; 25/25 real runs use the calculator). T-7b done 2026-11-10: Gemini client (`google-genai==3.0.0`, `anthropic` removed), internal format ↔ Gemini translation, `LLMUnavailableError`; 77 tests green locally and in Docker (no key), mutation-checked; whole app checked with real Gemini (two tools in one round, tool error, no tools). T-7b merged 2026-11-10. Manual end-to-end tests by the user on `main` (before T-8): all passed. T-8 done 2026-11-10 on `feat/history`: history replay (FR-21..23), message mapping moved to `schemas.py`, AC-59 exception removed; 80 tests green locally and in Docker (no key), mutation-checked (thinking filter, trim, final-answer source); real Gemini 4-turn chat with tools replays fine (all HTTP 200, follow-ups use earlier turns). T-8 merged 2026-11-10. The user's manual T-8 checks with real Gemini passed, and found that Gemini reported mock temperatures as °F → spec v0.8 (approved): weather description says °C, task T-8b done and merged 2026-11-10 (80 tests green locally and in Docker; 5/5 real runs say °C). T-9 done 2026-11-10 on `feat/datetime-tool`: datetime tool (`app/tools/datetime_tool.py`, injected clock, per-operation checks inside the tool as ToolError "Invalid input: ..."), registered as the 4th tool; 91 tests green locally and in Docker (no key), mutation-checked (6 mutations, one survivor fixed with a summer-clock test). Real Gemini in the container: current/convert/calculate (incl. negative minutes across a year boundary), weather + time in one round (AC-54 shape), and the unknown-timezone error all correct, HTTP 200. T-9 merged 2026-11-10. **Spec v0.9 (user's decision 2026-11-10: keep D4 as written):** SQLite's authorizer has a separate RECURSIVE action, so `WITH RECURSIVE` is rejected; AC-39 now uses a non-recursive cross join, AC-38 adds a recursive query. T-10 done 2026-11-10 on `feat/database-tool`: `app/sample_data.py` (seed 7, seed date from the app clock, idempotent, temp file + rename), `app/tools/database.py` (`mode=ro`, authorizer SELECT/READ/FUNCTION, 100 rows + `truncated`, 2 s progress-handler limit), registry gets the `sample.db` path from `app/main.py`; 110 tests green locally and in Docker (no key), mutation-checked (10 mutations; the `mode=ro` one survived at first, fixed with a test of the read-only connection alone). Real Gemini in the container: "orders last month" → 40 via `date('now', ...)` (AC-56 shape), joins, group-by, and a delete request answered as not allowed. T-10 merged 2026-11-10: milestone 3 reached (all 5 tools). **Spec v0.10 (user's decision 2026-11-10):** FR-17 also rejects fields outside the schema's `properties` ("Invalid input: unexpected field 'X'"); AC-17 extended. T-11 done 2026-11-10 on `feat/tool-robustness`: executor checks unknown tool, JSON Schema, unexpected fields, and one `TOOL_TIMEOUT_S` deadline per round (new setting, wired in `app/main.py`); chat service stops after 5 tool rounds ("Tool call limit reached", then one call with tool choice `none`, which always ends the loop). 120 tests green locally and in Docker (no key), mutation-checked (9 mutations, all caught). Test fix: tool `run` patches now use monkeypatch (the registry's TOOL objects are shared, so plain assignment leaked into later tests). Real Gemini re-run of the T-9/T-10 questions: all HTTP 200, no false "Invalid input". The loop now has a round cap. T-11 merged 2026-11-10. **Now: T-12** (LLM outcomes, Sonnet, branch `feat/llm-outcomes`, not created yet; waiting for the user's go-ahead). 

Separation of concerns (spec v0.5, NFR-12): rules in `CLAUDE.md` and architecture §2.1, enforced by `tests/test_architecture.py` (AC-59). Leak fixes: T-6 done (`LLMClient` takes plain values; prompt tool names from the registry), T-7 `LLMResult`, T-8 message mapping into `schemas.py` (done; `KNOWN_EXCEPTIONS` removed). D8: no repository layer.

## Open questions
| # | Question | Blocking? |
|---|---|---|
| Q1 | ~~Scope~~ Must items first, Nice deferred (see requirements §7) | No |
| Q2 | ~~Mock or real~~ Both mock; real weather deferred | No |
| G15 | ~~Streaming~~ Deferred to "if time" | No |
| Q3 | ~~Gap recommendations~~ All accepted | No |
| G6, G7 | ~~DB approach, limits~~ Decided in architecture §13 | No |
| Q4 | ~~Git init and commit style~~ Done 2026-11-10 (see Conventions) | No |
| Q5 | ~~No API key gives 500 + stuck `pending`~~ Approved 2026-11-10: FR-25 extended, AC-58 added, built in T-12 (spec v0.3) | No |
| Q7 | ~~Strict tool schemas reject `maxLength`?~~ No longer applies: spec v0.6 (scope review) dropped `strict`, so `input_schema` is sent unchanged. **Still open for stage 5:** the API account has no credits; offer the $5 credit option again before stage 5 (needed for AC-53..56 and a live demo) | No |
| Q6 | ~~Refusal fallbacks (beta)~~ Out of scope 2026-11-10: not in S1; FR-26 already handles refusals. At most a README "with more time" line in stage 6 | No |

## Later, if time allows (remind the user at the end of stage 5)
- Nice to have: custom tool registration, tool usage analytics, conversation summarization, rate limiting per tool (REQ-43..46)
- Real weather API instead of the mock (REQ-7)
- Streaming responses (REQ-39)

## Tasks
See `docs/chatbot-tasks.md`.

| Task | Status |
|---|---|
| T-1 skeleton | done 2026-11-10 |
| T-2 conversations | done 2026-11-10 |
| T-3 basic chat | done 2026-11-10 |
| T-4 calculator | done 2026-11-10 |
| T-5 mock tools | done 2026-11-10 |
| T-6 tool executor | done 2026-11-10 |
| T-7 tool loop | done 2026-11-10 (merged) |
| T-7b Gemini switch | done 2026-11-10 (merged) |
| T-8 history | done 2026-11-10 (merged) |
| T-8b weather unit | done 2026-11-10 (merged) |
| T-9 datetime tool | done 2026-11-10 (merged) |
| T-10 database tool | done 2026-11-10 (merged) |
| T-11 tool robustness | done 2026-11-10 (merged) |
| T-12..T-13 | not started |

## AI usage log
`docs/ai-usage-log.md` (entries so far: 24)

## Acceptance criteria results
- Pass: AC-1, AC-2, AC-3, AC-4, AC-6, AC-7, AC-8, AC-9, AC-11, AC-12, AC-22, AC-45, AC-46, AC-47 (also inside Docker; early AC-49 check: suite passes in the container without a key)
- Also pass: AC-31, AC-32, AC-34, AC-35, AC-61 (T-6)
- Also pass: AC-5, AC-13, AC-14, AC-16, AC-21, AC-44, AC-60 (T-7; 4 of the 6 required tests)
- T-7b (Gemini, spec v0.7): AC-62, AC-63 pass; AC-43, AC-47, AC-59, AC-60 rewritten for Gemini and pass. Docker suite: 77 passed without a key (NFR-3). `.env` port fixed by the user to `API_PORT=8001`; real container checked on it with real Gemini (two tools, tool error, no tools: all HTTP 200)
- T-9: AC-40, AC-41 pass (also in Docker)
- T-11 (spec v0.10): AC-15, AC-17, AC-18, AC-19, AC-20 pass; AC-33 now passes in full (201-char expression → "Invalid input:" via the executor)
- T-10 (spec v0.9): AC-36 (golden October count 40), AC-37, AC-38, AC-39 pass (also in Docker); AC-10, AC-42, AC-43 now pass in full
- T-8: AC-23 (required test 5), AC-24, AC-25 pass; AC-59 now passes in full (no exceptions)
- AC-10, AC-42, AC-43 now pass in full with all 5 tools (T-10)
- Milestone 1 Docker smoke test (T-3): `/health` ok, create conversation ok, blank content → 422, send without a key → 500 + stuck `pending` (Q5)
- Early Docker checks (T-1): health OK, runs as non-root `app`, writes `app.db` to the volume, `tzdata` timezones OK, healthcheck `healthy`
- Not run yet: the rest

## Decisions and changes since spec approval
| Date | Change | Spec version | Affected IDs |
|---|---|---|---|
| 2026-11-10 | Executor rejects fields outside the schema's `properties` (found in T-11: extra fields crashed the tool) | 0.10 | FR-17, AC-17, T-11 |
| 2026-11-10 | Keep D4's allow list; recursive queries rejected; AC-39 uses a cross join (found while starting T-10) | 0.9 | AC-38, AC-39, T-10 |
| 2026-11-10 | Weather description states °C (found in the user's manual T-8 test: Gemini guessed °F) | 0.8 | FR-29, AC-35, T-8b |
| 2026-11-10 | Scope review against S1: removed `strict` tool schemas, the `thinking` parameter and the `LLM_EFFORT` setting (effort fixed at `medium`); requirements doc fixed (status, REQ-51 for S1:30, Q numbering) | 0.6 | FR-33, FR-36, AC-43, AC-53, R9, Q7, REQ-51 |
| 2026-11-10 | Separation of concerns made explicit: NFR-12 (S1:30) + AC-59..61; FR-24 prompt tool names from the registry; architecture §2.1, D8; `CLAUDE.md` created; skill ground rule 12 | 0.5 | NFR-12, FR-24, AC-59, AC-60, AC-61, T-6, T-7, T-8 |
| 2026-11-10 | Q7: strict-mode-unsupported keywords (`maxLength` etc.) removed from `input_schema` only; AC-43, AC-53 extended | 0.4 | FR-33, AC-43, AC-53, R9 |
| 2026-11-10 | Q5: FR-25 also covers an LLM call that can't be made (no API key). New AC-58 in T-12 | 0.3 | FR-25, AC-58, T-12 |
| 2026-11-10 | Host port made configurable (`API_PORT`, default 8000) because port 8000 was taken on this machine. Deployment detail only, no behavior change | 0.2 | NFR-2 (AC-48 uses `API_PORT` if 8000 is taken) |
