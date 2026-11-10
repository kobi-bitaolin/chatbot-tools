# Chatbot Tools: Task List

- **Spec:** `docs/chatbot-spec.md` v0.2 (Approved 2026-11-10)
- **Status:** Draft, awaiting approval
- **Date:** 2026-11-10

**Rules for every task** (S3, spec §10)
- Work on its own branch from `main`.
- Red: write the AC tests first and see them fail for the right reason.
- Green: write the minimum code. Then refactor, and run the full suite.
- Explain the code in 2-4 lines and add any AI usage log entry.
- One commit, merged into `main` when everything is green, then delete the branch.
- **Done** = the task's AC tests pass and the full suite is green.

**Model column:** the Claude Code model I recommend for doing the task. Switch with `/model` before the task starts.
- Sonnet for clear, routine work.
- Opus for the parts the interview will dig into, and for concurrency and security.

Order: the assignment's tips (S1:419-424). Basic chat → calculator → tool loop → more tools → errors last.

| Task | Branch | Description | FR / NFR | AC | Depends on | Model |
|---|---|---|---|---|---|---|
| T-1 | `chore/skeleton` | Project skeleton: folders (S3 §7), pinned `requirements.txt`, `config.py` (pydantic-settings), `create_app(settings)`, `/health`, DB engine and session, `conftest.py` (temp files, unset key, socket block), Dockerfile (non-root, `/app/data` chown, tzdata), docker-compose.yml, `.env.example`. **Early check:** `docker compose up --build`, then `/health` and a write to `/app/data` (R6, R12) | FR-35, NFR-1, NFR-3, NFR-7, NFR-9 | 45, 47 | none | Sonnet |
| T-2 | `feat/conversations` | ORM models (Conversation, Message, ToolExecution, cascades), conversation service, routes: create, list, get, delete, reset; 404s | FR-1..7, NFR-4 | 1, 4, 6, 7, 46 | T-1 | Sonnet |
| T-3 | `feat/basic-chat` | LLM client wrapper (lazy creation), fake LLM (scripted blocks and stop reasons, request recording, SDK errors), chat service without tools: send endpoint, content validation, D0 system prompt, first message, `last_message_at` | FR-6, FR-8, FR-9, FR-11, FR-20, FR-24 | 2, 3, 8, 9, 10, 11, 12, 22 | T-2 | **Opus** |
| T-4 | `feat/calculator` | Calculator tool: `ast` whitelist, `^`, float-only math, finite checks, limits, all error strings | FR-27, NFR-5 | 31, 32, 33 | T-1 | **Opus** |
| T-5 | `feat/mock-tools` | Web search mock (keyword results) and weather mock (injectable generator, ranges) | FR-28, FR-29 | 34, 35 | T-1 | Sonnet |
| T-6 | `feat/tool-executor` | Tool base and registry (S1 format → `input_schema`, `strict`), `GET /tools`, executor core: module-level thread pool, `ToolResult`, error catching, request order; LLM request settings | FR-32, FR-33, FR-36 | 42, 43 | T-3, T-4, T-5 | **Opus** |
| T-7 | `feat/tool-loop` | The tool loop: rounds, all results in one message, `tool_use_id` pairing, `tools_used`, ToolExecution logging per round, token sum, `pending` → `complete`. **Includes 4 of the 6 required tests** | FR-10, FR-12, FR-13, FR-14, FR-16, FR-19, FR-34 | 5, 13, 14, 16, 21, 44 | T-6 | **Opus** |
| T-8 | `feat/history` | Multi-turn replay rule (FR-21): `llm_blocks` stored as received, thinking removed on replay, 20-turn trim at turn boundaries. **Required test 5** | FR-21, FR-22, FR-23 | 23, 24, 25 | T-7 | **Opus** |
| T-9 | `feat/datetime-tool` | Datetime tool: current, convert, calculate, injected clock, per-operation checks, offsets, unknown timezone | FR-31, FR-17 (datetime part) | 40, 41 | T-6 | Sonnet |
| T-10 | `feat/database-tool` | Sample DB seeder (seed date, seed 7, idempotent) and database tool: read-only `mode=ro`, authorizer (SELECT/READ/FUNCTION), 100-row limit, `truncated`, progress-handler time limit | FR-30, NFR-6, NFR-10 | 36, 37, 38, 39 | T-6 | **Opus** |
| T-11 | `feat/tool-robustness` | Executor robustness: JSON Schema validation ("Invalid input:"), unknown tool, round deadline timeout with partial results, round limit with `tool_choice: none` | FR-15, FR-16, FR-17, FR-18, NFR-8 | 15, 17, 18, 19, 20 | T-7 | **Opus** |
| T-12 | `feat/llm-outcomes` | LLM outcomes: 502 on SDK errors, `error` status, refusal, `max_tokens`, unexpected stop reason, failed-turn skip, refusal replay | FR-25, FR-26, FR-3 (error messages) | 26, 27, 28, 29, 30, 57 | T-8 | Sonnet |
| T-13 | `test/real-llm` | Real-LLM checks as tests marked `@pytest.mark.real_llm`, skipped without a key. They're written here and run in stage 5 | FR-10, FR-12, FR-13, FR-21, FR-22, FR-30 | 53, 54, 55, 56 | T-12 | Sonnet |

**Milestones (I'll pause and report at each one)**
1. After **T-3**: the basic chat slice works end to end with the fake LLM, and the API runs in Docker.
2. After **T-7**: the tool loop works, and 4 of the 6 required tests pass.
3. After **T-10**: all 5 tools are done.
4. After **T-13**: all tasks are done. I stop for approval, then stage 5.

**Real LLM in stage 4:** none in automated tests. After T-7 I'll suggest **one** manual curl with your API key to check R1 (does the LLM really call the calculator?). That's optional and costs a few cents.

## Coverage check

- **AC coverage:**
  - Automated ACs 1-47 and 57 all belong to exactly one task.
  - Real-LLM ACs 53-56 are written in T-13 and run in stage 5.
  - Manual ACs 48-52 are stage 5/6 checks (Docker, secrets, README). AC-48's Docker part is started early in T-1.
- **FR-1..36 and NFR-1..11:** every one appears in at least one task, or in stage 5/6 (NFR-2 → AC-48, NFR-11 → AC-52).
- **No task without a requirement:** every task lists its FR/NFR and AC.
- **Required tests:** AC-10 (T-3), AC-13, 14, 16, 44 (T-7), AC-23 (T-8).
