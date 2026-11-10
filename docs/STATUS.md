# Project status: chatbot-tools

- **Spec:** `docs/chatbot-spec.md` (v0.7, Approved, 2026-11-10)
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
- **Current stage:** 4b, TDD implementation, T-1..T-7 merged; T-7b (Gemini switch) done on `feat/gemini-llm`, waiting for the merge yes
- **Last updated:** 2026-11-10

## Next action
Stages 1-3 and the task list approved 2026-11-10. T-1..T-6 done and merged (T-6 merged 2026-11-10, incl. the v0.6 scope cuts; FR-26 kept in full after the scope review). T-7 (tool loop + neutral `LLMResult`) merged 2026-11-10, all 65 tests green, mutation-checked. Milestone 2 reached. **Provider change (2026-11-10):** the user switched the LLM to Google Gemini; **spec v0.7 approved 2026-11-10** (D9, FR-37, AC-62/63, task T-7b). Real Gemini checked with a scratchpad probe (key in `.env`): single tool, two tools in one round, no tools, tool error all work. Risk R1 fixed in v0.7 (calculator description + D0 wording; 25/25 real runs use the calculator). T-7b done 2026-11-10: Gemini client (`google-genai==3.0.0`, `anthropic` removed), internal format ↔ Gemini translation, `LLMUnavailableError`; 77 tests green locally and in Docker (no key), mutation-checked; whole app checked with real Gemini (two tools in one round, tool error, no tools). **Now: merge T-7b (needs a yes), then T-8** (history, Opus). Note: until T-11 adds the round limit (FR-15), the loop has no cap.

Separation of concerns (spec v0.5, NFR-12): rules in `CLAUDE.md` and architecture §2.1, enforced by `tests/test_architecture.py` (AC-59). Leak fixes: T-6 done (`LLMClient` takes plain values; prompt tool names from the registry), T-7 `LLMResult`, T-8 message mapping into `schemas.py` (then remove the `KNOWN_EXCEPTIONS` entry in the test). D8: no repository layer.

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
| T-7b Gemini switch | done 2026-11-10 (on branch, merge pending) |
| T-8..T-13 | not started |

## AI usage log
`docs/ai-usage-log.md` (entries so far: 16)

## Acceptance criteria results
- Pass: AC-1, AC-2, AC-3, AC-4, AC-6, AC-7, AC-8, AC-9, AC-11, AC-12, AC-22, AC-45, AC-46, AC-47 (also inside Docker; early AC-49 check: suite passes in the container without a key)
- Also pass: AC-31, AC-32, AC-34, AC-35, AC-61 (T-6)
- Also pass: AC-5, AC-13, AC-14, AC-16, AC-21, AC-44, AC-60 (T-7; 4 of the 6 required tests)
- T-7b (Gemini, spec v0.7): AC-62, AC-63 pass; AC-43, AC-47, AC-59, AC-60 rewritten for Gemini and pass. Docker suite: 77 passed without a key (NFR-3). Note: `.env` has `API_PORT=80001` (invalid, max 65535); Docker was run with `API_PORT=8001` for the check
- Partly: AC-10, AC-42, AC-43 (all pass for the 3 registered tools; "5 tools" once T-9/T-10 add datetime and database); AC-59 (passes; the routes/`app.models` rule is a known exception until T-8); AC-33 (attack inputs and no `eval(`/`exec(` pass; the 201-char "Invalid input:" check goes through the executor's schema validation, added in T-11)
- Milestone 1 Docker smoke test (T-3): `/health` ok, create conversation ok, blank content → 422, send without a key → 500 + stuck `pending` (Q5)
- Early Docker checks (T-1): health OK, runs as non-root `app`, writes `app.db` to the volume, `tzdata` timezones OK, healthcheck `healthy`
- Not run yet: the rest

## Decisions and changes since spec approval
| Date | Change | Spec version | Affected IDs |
|---|---|---|---|
| 2026-11-10 | Scope review against S1: removed `strict` tool schemas, the `thinking` parameter and the `LLM_EFFORT` setting (effort fixed at `medium`); requirements doc fixed (status, REQ-51 for S1:30, Q numbering) | 0.6 | FR-33, FR-36, AC-43, AC-53, R9, Q7, REQ-51 |
| 2026-11-10 | Separation of concerns made explicit: NFR-12 (S1:30) + AC-59..61; FR-24 prompt tool names from the registry; architecture §2.1, D8; `CLAUDE.md` created; skill ground rule 12 | 0.5 | NFR-12, FR-24, AC-59, AC-60, AC-61, T-6, T-7, T-8 |
| 2026-11-10 | Q7: strict-mode-unsupported keywords (`maxLength` etc.) removed from `input_schema` only; AC-43, AC-53 extended | 0.4 | FR-33, AC-43, AC-53, R9 |
| 2026-11-10 | Q5: FR-25 also covers an LLM call that can't be made (no API key). New AC-58 in T-12 | 0.3 | FR-25, AC-58, T-12 |
| 2026-11-10 | Host port made configurable (`API_PORT`, default 8000) because port 8000 was taken on this machine. Deployment detail only, no behavior change | 0.2 | NFR-2 (AC-48 uses `API_PORT` if 8000 is taken) |
