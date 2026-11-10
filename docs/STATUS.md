# Project status: chatbot-tools

- **Spec:** `docs/chatbot-spec.md` (v0.2, Approved, 2026-11-10)
- **Source:** `chatbot-tool.md` (S1)
- **Conventions (Git, agreed 2026-11-10):**
  - `main` always works; only tested work is merged into it.
  - One short-lived branch per feature (`feat/basic-chat`, `feat/calculator`, ...), merged into `main` when all tests pass, then deleted.
  - One commit per task, Conventional Commits with IDs, e.g. `feat(calculator): safe expression parser (FR-5, AC-7)`. Prefixes: feat, fix, test, docs, chore.
  - `docs/` is committed. `chatbot-tool.md`, `.env`, and DB files are git-ignored.
  - Remote: private repo https://github.com/kobi-bitaolin/chatbot-tools (created 2026-11-10).
  - **Standing yes (2026-11-10):** push `main` to `origin` after every merged task. Anything else (other branches, force-push, changing visibility, adding collaborators) needs a fresh yes. Make it public / share only at stage 6 with a fresh yes.
- **Current stage:** 4b, TDD implementation, T-1 done; next T-2
- **Last updated:** 2026-11-10

## Next action
Stages 1-3 and the task list approved 2026-11-10. T-1 done. Next: T-2 (data model + conversation endpoints), recommended model Sonnet.

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
See `docs/chatbot-tasks.md`.

| Task | Status |
|---|---|
| T-1 skeleton | done 2026-11-10 |
| T-2..T-13 | not started |

## AI usage log
`docs/ai-usage-log.md` (entries so far: 1)

## Acceptance criteria results
- Pass: AC-45, AC-47 (also inside Docker; early AC-49 check: suite passes in the container without a key)
- Early Docker checks (T-1): health OK, runs as non-root `app`, writes `app.db` to the volume, `tzdata` timezones OK, healthcheck `healthy`
- Not run yet: the rest

## Decisions and changes since spec approval
| Date | Change | Spec version | Affected IDs |
|---|---|---|---|
| 2026-11-10 | Host port made configurable (`API_PORT`, default 8000) because port 8000 was taken on this machine. Deployment detail only, no behavior change | 0.2 | NFR-2 (AC-48 uses `API_PORT` if 8000 is taken) |
