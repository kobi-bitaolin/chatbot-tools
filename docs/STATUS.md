# Project status: chatbot-tools

- **Spec:** `docs/chatbot-spec.md` (v0.3, Approved, 2026-11-10)
- **Source:** `chatbot-tool.md` (S1)
- **Conventions (Git, agreed 2026-11-10):**
  - `main` always works; only tested work is merged into it.
  - One short-lived branch per feature (`feat/basic-chat`, `feat/calculator`, ...), merged into `main` when all tests pass, then deleted.
  - One commit per task, Conventional Commits with IDs, e.g. `feat(calculator): safe expression parser (FR-5, AC-7)`. Prefixes: feat, fix, test, docs, chore.
  - `docs/` is committed. `chatbot-tool.md`, `.env`, and DB files are git-ignored.
  - Remote: private repo https://github.com/kobi-bitaolin/chatbot-tools (created 2026-11-10).
  - **Standing yes (2026-11-10):** push `main` to `origin` after every merged task. Anything else (other branches, force-push, changing visibility, adding collaborators) needs a fresh yes. Make it public / share only at stage 6 with a fresh yes.
  - **Merges need a yes per task** (2026-11-10: the user declined a standing yes for merge + branch delete).
- **Current stage:** 4b, TDD implementation, T-1..T-4 done; next T-5
- **Last updated:** 2026-11-10

## Next action
Stages 1-3 and the task list approved 2026-11-10. T-1..T-3 done and merged; Milestone 1 approved 2026-11-10. T-4 done and merged. Next: T-5 (web search and weather mocks, Sonnet).

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
| T-5..T-13 | not started |

## AI usage log
`docs/ai-usage-log.md` (entries so far: 10)

## Acceptance criteria results
- Pass: AC-1, AC-2, AC-3, AC-4, AC-6, AC-7, AC-8, AC-9, AC-11, AC-12, AC-22, AC-45, AC-46, AC-47 (also inside Docker; early AC-49 check: suite passes in the container without a key)
- Also pass: AC-31, AC-32
- Partly: AC-10 (shape, 1 call, `tool_choice: auto` pass; the "5 tools" check is added in T-6 when the tools exist); AC-33 (attack inputs and no `eval(`/`exec(` pass; the 201-char "Invalid input:" check goes through the executor's schema validation, added in T-11)
- Milestone 1 Docker smoke test (T-3): `/health` ok, create conversation ok, blank content → 422, send without a key → 500 + stuck `pending` (Q5)
- Early Docker checks (T-1): health OK, runs as non-root `app`, writes `app.db` to the volume, `tzdata` timezones OK, healthcheck `healthy`
- Not run yet: the rest

## Decisions and changes since spec approval
| Date | Change | Spec version | Affected IDs |
|---|---|---|---|
| 2026-11-10 | Q5: FR-25 also covers an LLM call that can't be made (no API key). New AC-58 in T-12 | 0.3 | FR-25, AC-58, T-12 |
| 2026-11-10 | Host port made configurable (`API_PORT`, default 8000) because port 8000 was taken on this machine. Deployment detail only, no behavior change | 0.2 | NFR-2 (AC-48 uses `API_PORT` if 8000 is taken) |
