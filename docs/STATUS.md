# Project status: chatbot-tools

- **Spec:** `docs/chatbot-spec.md` (v0.2, Approved, 2026-11-10)
- **Source:** `chatbot-tool.md` (S1)
- **Conventions (Git, agreed 2026-11-10):**
  - `main` always works; only tested work is merged into it.
  - One short-lived branch per feature (`feat/basic-chat`, `feat/calculator`, ...), merged into `main` when all tests pass, then deleted.
  - One commit per task, Conventional Commits with IDs, e.g. `feat(calculator): safe expression parser (FR-5, AC-7)`. Prefixes: feat, fix, test, docs, chore.
  - `docs/` is committed. `chatbot-tool.md`, `.env`, and DB files are git-ignored.
  - Never push without an explicit yes. Remote: private GitHub repo, not set up yet.
- **Current stage:** 4a, task list, awaiting approval
- **Last updated:** 2026-11-10

## Next action
Stages 1-3 approved 2026-11-10. Task list `docs/chatbot-tasks.md` (T-1..T-13) awaiting approval. Then T-1 (skeleton) on Sonnet.

## Open questions
| # | Question | Blocking? |
|---|---|---|
| Q1 | ~~Scope~~ Must items first, Nice deferred (see requirements §7) | No |
| Q2 | ~~Mock or real~~ Both mock; real weather deferred | No |
| G15 | ~~Streaming~~ Deferred to "if time" | No |
| Q3 | ~~Gap recommendations~~ All accepted | No |
| G6, G7 | ~~DB approach, limits~~ Decided in architecture §13 | No |
| Q4 | ~~Git init and commit style~~ Done 2026-11-10 (see Conventions) | No |

## Later, if time allows (remind the user at the end of stage 5)
- Nice to have: custom tool registration, tool usage analytics, conversation summarization, rate limiting per tool (REQ-43..46)
- Real weather API instead of the mock (REQ-7)
- Streaming responses (REQ-39)

## Tasks
See `docs/chatbot-tasks.md`. All 13 tasks: not started.

## AI usage log
`docs/ai-usage-log.md` (entries so far: 1)

## Acceptance criteria results
None yet.

## Decisions and changes since spec approval
| Date | Change | Spec version | Affected IDs |
|---|---|---|---|
