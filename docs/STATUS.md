# Project status: chatbot-tools

- **Spec:** `docs/chatbot-spec.md` (not written yet; stage 3)
- **Source:** `chatbot-tool.md` (S1)
- **Conventions (Git, agreed 2026-11-10):**
  - `main` always works; only tested work is merged into it.
  - One short-lived branch per feature (`feat/basic-chat`, `feat/calculator`, ...), merged into `main` when all tests pass, then deleted.
  - One commit per task, Conventional Commits with IDs, e.g. `feat(calculator): safe expression parser (FR-5, AC-7)`. Prefixes: feat, fix, test, docs, chore.
  - `docs/` is committed. `chatbot-tool.md`, `.env`, and DB files are git-ignored.
  - Never push without an explicit yes. Remote: private GitHub repo, not set up yet.
- **Current stage:** 1, requirements intake, awaiting answers and approval
- **Last updated:** 2026-11-10

## Next action
User answers Q1-Q4 and approves `docs/chatbot-requirements.md`. Then stage 2 (architecture).

## Open questions
| # | Question | Blocking? |
|---|---|---|
| Q1 | Which Should/Nice items are in scope | Yes (architecture) |
| Q2 | Mock or real web search and weather | Yes (architecture) |
| Q3 | Accept recommendations for gaps G1-G13 | Yes |
| Q4 | ~~Git init and commit style~~ Done 2026-11-10 (see Conventions) | No |

## Tasks
None yet (stage 4).

## AI usage log
`docs/ai-usage-log.md` (entries so far: 1)

## Acceptance criteria results
None yet.

## Decisions and changes since spec approval
| Date | Change | Spec version | Affected IDs |
|---|---|---|---|
