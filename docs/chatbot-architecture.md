# Chatbot Tools: Architecture

- **Source (S1):** `chatbot-tool.md`. **Requirements:** `docs/chatbot-requirements.md` (approved 2026-11-10)
- **Stage:** 2, architecture
- **Status:** Draft v2 (self-review + independent review applied), awaiting approval
- **Date:** 2026-11-10

Guiding rule: keep it as small as possible and explainable line by line. The design follows the S1 diagram (S1:74-96): Chat API → LLM → Tool Executor → final response.

---

## 1. Stack

| Choice | Decision | Why | Rejected alternative |
|---|---|---|---|
| Language | **Python 3.12** (Docker image `python:3.12-slim`) | Fixed by S1:341 (3.11+). 3.12 is stable and has good error messages | 3.13: newer, and some libraries lag behind |
| Web framework | **FastAPI** + Uvicorn, **plain `def` routes** (not `async def`) | Pydantic validation (part of REQ-30), automatic `/docs` page, `TestClient`. Plain `def` routes run in FastAPI's thread pool, so the synchronous Anthropic SDK never blocks the server | `async def` routes: calling the sync SDK inside them would freeze every other request. Flask: no built-in validation |
| LLM | **Claude via the official `anthropic` Python SDK**, model from env `LLM_MODEL`, default `claude-opus-5-5` | Native function calling, typed errors, usage counts. A cheaper model is a one-line `.env` change; your decision | LangChain/agent frameworks: they hide the tool loop the interview asks about (S1:27) |
| Tool loop | **Hand-written loop** | Needed for per-call timeouts, DB logging, a max-rounds limit, and the exact `tools_used` format. Shows you understand function calling | SDK Tool Runner (beta): less code, but a "black box" for the interview |
| App storage | **SQLite + SQLAlchemy 2.0**, file on a Docker volume | Zero setup, survives restarts (G10), models map 1:1 to the S1 data model | PostgreSQL: an extra container with no benefit at this size |
| Sample data | **Separate SQLite file** `sample.db` | The DB tool can never touch conversations (security) | Same file as app data |
| Validation | **`jsonschema`** library in the executor | Checks every tool input against its definition, independently of the LLM | Trusting the LLM's arguments |
| Tests | **pytest** + `TestClient` + a **fake LLM** (section 11) | Repeatable, free, no network, no API key needed | Real LLM in tests: flaky, costs money |
| Config | **pydantic-settings** from env vars; `.env.example` documents them. The API key is optional at startup and only needed when the real LLM is called | No secrets in the repo, and tests run without a key | Hard-coded config |

## 2. Components

| Component | File | Responsibility |
|---|---|---|
| API routes | `app/api/routes.py` | HTTP only: parse, call a service, return, map errors to status codes. No business rules |
| Schemas | `app/schemas.py` | Pydantic request/response models in the S1 formats |
| Conversation service | `app/services/conversations.py` | Create / list / get / delete / reset |
| Chat service (orchestrator) | `app/services/chat.py` | The tool loop (section 4). **The only place that writes to the app DB during a turn** |
| LLM client | `app/llm/client.py` | Thin wrapper around the SDK: `complete(system, messages, tools, tool_choice)`. Created lazily on first use, so the app and tests start without an API key. The fake LLM implements the same method |
| Tool base | `app/tools/base.py` | Shared tool shape (section 3) |
| Tool registry | `app/tools/registry.py` | Holds all tools; gives definitions to the LLM and to `GET /tools` |
| Tool executor | `app/tools/executor.py` | Validates input, runs tools in parallel with a timeout, measures time, catches errors, returns `ToolResult`s. **Never raises, and never touches the app DB** |
| Tools | `app/tools/calculator.py`, `web_search.py`, `weather.py`, `database.py`, `datetime_tool.py` | One file per tool, pure logic |
| Storage | `app/db.py`, `app/models.py` | Engine, one session per request, ORM models (section 5) |
| Sample DB | `app/sample_data.py` | Creates and seeds `sample.db` (section 5) |
| Config | `app/config.py` | Settings: API key, model, limits, DB paths |

### 2.1 Layers and responsibilities (separation of concerns, NFR-12)

Each layer has one job, so it has one reason to change.

| Layer | Files | Its one job | Must not |
|---|---|---|---|
| HTTP | `app/api/` | Parse requests, call a service, shape the response | Hold business rules, query the DB, import `app.models` (from T-8) |
| Validation | `app/schemas.py` | Request/response shapes, including the DB-row → response mapping (from T-8) | Touch the DB |
| Business rules | `app/services/` | Conversations and one chat turn (orchestration) | Import `fastapi` or `anthropic`; read SDK objects |
| LLM | `app/llm/` | Talk to the provider; turn its response into a neutral `LLMResult` (from T-7) | Import `app.config` (it gets plain values) |
| Tools | `app/tools/` | Pure tool logic, registry, executor | Import anything from the app outside `app.tools` |
| Data | `app/db.py`, `app/models.py` | Tables, engine, sessions | Hold rules |
| Wiring | `app/main.py`, `app/config.py` | Read settings, build the objects, connect the layers, map service errors to HTTP codes | Hold rules |

**Import direction:** api → services → (tools, llm, models). Only `app/main.py` knows every layer. `tests/test_architecture.py` (AC-59) fails on a forbidden import, so the rule holds without anyone remembering it.

**Why it pays here:** switching LLM provider touches only `app/llm/`; adding a tool touches only `app/tools/` (the prompt and `GET /tools` read the registry); the fake LLM and the injected clock work because services receive their dependencies instead of creating them.

## 3. Tools

### 3.1 Shared interface

```python
class Tool:
    name: str                    # "calculator"
    description: str             # tells the LLM when to use it (drives tool selection, D1)
    parameters: dict             # JSON Schema in the S1:102-119 format
    def run(self, **kwargs) -> dict   # returns the "output" dict, or raises ToolError
```

The executor wraps every run into a `ToolResult` in the S1:121-131 format, plus `error` (G3):

```json
{"tool": "calculator", "input": {"expression": "1/0"}, "output": null,
 "success": false, "error": "Division by zero", "execution_time_ms": 1}
```

Format translation: S1 calls the schema `parameters`, while the Anthropic API calls it `input_schema`. The registry stores the S1 format and renames `parameters` to `input_schema` in one place; the schema itself is sent unchanged (spec v0.6: no `strict` mode, since S1 doesn't ask for it and the executor validates every input anyway).

### 3.2 Executor

1. **Look up** the tool. If it's unknown → error result "Unknown tool".
2. **Validate** the input with `jsonschema`, plus the tool's own extra checks (for example the datetime fields per operation, section 3.3). If invalid → error result with the validation message (REQ-30).
3. **Run** all valid calls of one round in parallel on a **single module-level `ThreadPoolExecutor`** (max 8 workers). It's created once and never shut down per request.
4. **Wait** for each future with `future.result(timeout=remaining)`, against one deadline of `TOOL_TIMEOUT_S` (5 s) for the round. A call that isn't done becomes "Timed out after 5s". The response does not wait for it. Python can't kill a thread, so it finishes in the background and its result is ignored. (A `with ThreadPoolExecutor()` block is *not* used, because leaving the block waits for every thread and would defeat the timeout.)
5. **Return** the results **in the same order as the LLM's `tool_use` blocks**, not in completion order, so `tools_used` and `tool_result` are deterministic.

Tools never write to the app DB. They return results to the orchestrator thread, which logs them (SQLAlchemy sessions are not thread-safe).

### 3.3 Tool details

| Tool | Input | Output | Notes |
|---|---|---|---|
| calculator | `expression: str` (max 200 chars) | `{"result": float}` | **Safe parser, no `eval`**: Python's `ast` with a whitelist of numbers, + − × ÷ % `**`, unary −, parentheses, and `math` functions/constants (sqrt, sin, cos, tan, log, log10, exp, abs, round, pi, e). `^` becomes `**` (S1:179). Limits: exponent ≤ 1000 in absolute value, nesting depth ≤ 20. Errors: invalid expression, division by zero, result too large |
| web_search | `query: str` | `{"results": [{title, snippet, url}]}` | Mock: predefined results matched by keyword. No match → empty list (not an error) |
| weather | `location: str` | `{"location", "temperature", "condition", "humidity"}` | Mock: realistic random values. The random generator is injected, so tests can fix it |
| database_query | `sql: str` (one SELECT) | `{"columns": [...], "rows": [...], "row_count": n}` | **Deliberate deviation from S1:204**, which says the input is natural language. Here the LLM is the translator from natural language to SQL. The tool description contains the table schemas. Dates like "last month" use SQLite `date('now', ...)`. Each call opens its own read-only connection (thread-safe). Security in D4 |
| datetime | `operation: "current" \| "convert" \| "calculate"`, optional `timezone`, `datetime`, `from_tz`, `to_tz`, `days`, `hours`, `minutes` | `{"result": "2026-11-10T14:30:00+02:00", ...}` | Per-operation checks in the executor: `current` needs nothing (`timezone` optional, default UTC). `convert` needs `datetime`, `from_tz` and `to_tz`. `calculate` needs `datetime` and at least one of `days`/`hours`/`minutes`. Uses `zoneinfo`. The **`tzdata` package is required** in Docker (R6). The clock is injected for tests |

## 4. Orchestration loop

One user message is one **turn**. A turn can have several LLM **rounds**.

```
POST /conversations/{id}/messages {"content": "..."}

FastAPI validates the body first (422 if content is missing, empty or only spaces;
content is stripped). Then:

 1. Load the conversation (404 if missing).
 2. Save the user message. Create the assistant message with status "pending".
    Set conversation.last_message_at.
 3. Build the LLM input: system prompt (D0) + history (D5) + the new user message.
 4. tool_rounds = 0
    loop:
      response = LLM(messages, tools, tool_choice=auto)
      add response.usage to the turn's token total
      if response.stop_reason == "tool_use" and tool_rounds < MAX_TOOL_ROUNDS (5):
          results = executor.run_all(tool_use blocks)            # parallel, timeout
          log each result as a ToolExecution row (orchestrator thread)
          append the assistant response (all blocks, thinking included, unchanged)
          append ONE user message with all tool_result blocks (failures: is_error true)
          tool_rounds += 1
          continue
      if response.stop_reason == "tool_use":                     # round limit reached
          append assistant response + tool_results, then make ONE final call
          with tool_choice=none, so the LLM must answer in text
          (it runs through the checks below)
      break
 5. Outcome by stop_reason of the last response:
      "end_turn"    → status "complete", content = the text
      "refusal"     → status "complete", content = "I can't help with that request."
      "max_tokens"  → status "complete", content = the text so far + " [response cut off]"
      anything else → status "error",    content = "Unexpected LLM response"
 6. Save content, tools_used, tokens_used, llm_blocks on the assistant message.
    Set conversation.last_message_at.
 7. Return {message, tools_used, tokens_used}.
```

**Failure paths**

| What fails | What happens | Requirement |
|---|---|---|
| Tool raises an error | Error result → sent to the LLM as `is_error: true` → the LLM explains it to the user | REQ-28 |
| Invalid tool parameters | Validation error result, same path | REQ-30 |
| Tool times out | That call fails with "Timed out after 5s". Other calls in the round keep their results (partial results, G9) | REQ-31 |
| Unknown tool | Error result "Unknown tool", same path | REQ-30 |
| LLM keeps calling tools | After 5 tool rounds, a final call with `tool_choice: none` | REQ-32 |
| LLM API error (network, 429, 5xx) | The SDK retries twice. Still failing → HTTP 502 with a clear message. The assistant message gets status "error". Tool executions already done stay logged | REQ-26 |
| Unexpected stop reason | Status "error", HTTP 502 | robustness |
| Conversation not found | 404 | REQ-19/20 |

Why all results go back in one message: the Claude docs say that splitting parallel results across messages teaches the model to stop making parallel calls (REQ-29).

## 5. Data model

Two SQLite files in `/app/data`: `app.db` (below) and `sample.db` (tool data).

**App engine settings:** `check_same_thread=False` (plain `def` routes run in a thread pool), and one SQLAlchemy session per request.

**Conversation**: `id` (str, `conv_` + random hex, G12), `system_prompt` (text, nullable), `created_at`, `last_message_at` (nullable, set every time a message is saved).

**Message**: `id`, `conversation_id` (FK), `role` (`user` / `assistant`), `content`, `tools_used` (JSON, nullable), `tokens_used` (int, nullable), `llm_blocks` (JSON, nullable), `status` (`pending` / `complete` / `error`, assistant only), `created_at`.
- The system prompt lives on the Conversation (G13). `system` stays an allowed role, as S1:296 lists it, but it isn't used.
- **Additions to S1:**
  - `llm_blocks` stores the turn's raw assistant and tool blocks, for replay (D5).
  - `status` makes failures visible and keeps them out of replay.

**ToolExecution**: `id`, `message_id` (FK to the turn's assistant message), `tool_name`, `input` (JSON), `output` (JSON, nullable), `success`, `error_message` (nullable), `execution_time_ms`, `created_at`. Executions are saved by the orchestrator right after each round, linked to the `pending` assistant message, so nothing is lost if the LLM fails later (REQ-26).

**Deletes:** the SQLAlchemy relationships use `cascade="all, delete-orphan"` (Conversation → Messages → ToolExecutions). This doesn't depend on SQLite's foreign-key setting, which is off by default.
- Delete conversation removes all three levels.
- Reset removes messages and executions, and keeps the conversation and its system prompt.
- Tests check that no orphan rows are left.

**Sample DB:**
- Tables: `users` (~50), `products` (~30), `orders` (~500 over the 12 months before the seed date), `order_items`.
- Fixed random seed, and the **seed date is a parameter**. Tests pass a fixed date, so a "last month" count is exactly known. The app passes today's date.
- Seeding is **idempotent**: `sample.db` is created only if it doesn't exist, so the data doesn't change across restarts.

## 6. Endpoints

| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| POST | `/conversations` | `{"system_prompt"?: str}` | 201 `{id, created_at}` | 422 |
| GET | `/conversations` | none | 200 `{"conversations": [{id, created_at, last_message_at, message_count}]}` | none |
| GET | `/conversations/{id}` | none | 200 `{id, system_prompt, messages: [{role, content, status?, tools_used?, tokens_used?, created_at}], created_at}` | 404 |
| DELETE | `/conversations/{id}` | none | 204 | 404 |
| POST | `/conversations/{id}/reset` | none | 200 `{id, message_count: 0}` | 404 |
| POST | `/conversations/{id}/messages` | `{"content": str}` (1-10,000 chars after stripping) | 200 `{message: {role, content}, tools_used: [...], tokens_used}` | 422, 404, 502 |
| GET | `/tools` | none | 200 `{"tools": [{name, description, parameters}]}` | none |
| GET | `/health` | none | 200 `{"status": "ok"}` | none |

- **422 comes before 404**, because FastAPI validates the body before the handler runs.
- **History shows every message**, including `error` ones with their `status`, so failures are visible. `pending` only appears while a request is in flight. Refused turns are `complete` and are replayed like normal turns.
- **Additions to S1:** `/health` (Docker health check), `parameters` in `GET /tools` (shows each tool's inputs), and `status` in history.

## 7. Folder structure

```
chatbot-tools/
├── app/
│   ├── main.py            # FastAPI app; startup creates tables and seeds sample.db if missing
│   ├── config.py  db.py  models.py  schemas.py  sample_data.py
│   ├── api/routes.py
│   ├── services/conversations.py  chat.py
│   ├── llm/client.py
│   └── tools/base.py  registry.py  executor.py
│       calculator.py  web_search.py  weather.py  database.py  datetime_tool.py
├── tests/
│   ├── conftest.py        # temp DB files, TestClient, fake LLM, fixed clock/seed
│   ├── fake_llm.py
│   ├── test_tools_*.py  test_executor.py  test_api_*.py
├── docs/
├── Dockerfile  docker-compose.yml  requirements.txt  .env.example
├── README.md  AI_USAGE.md  .gitignore  .gitattributes
```

## 8. Key decisions (for the README, S1:313-321)

**D0: System prompt.** The text sent to the LLM is always built the same way:
- our fixed app instructions (for example "Use a tool whenever it gives a more accurate answer than you can"),
- then a blank line,
- then the client's `system_prompt` from `POST /conversations`, or "You are a helpful assistant." when none was given.

It is stored once per conversation and **never contains changing values** such as today's date. So it's byte-identical every turn, which keeps replay valid (D5). The LLM gets the date from the datetime tool or from SQL `date('now')`.

**D1: Tool selection.** The LLM decides, from the tool descriptions and the D0 instructions, with `tool_choice: auto`. Each description says what the tool does and when to use it, for example: "Use for any arithmetic; never calculate in your head." Current Claude Opus/Sonnet models reject *forced* tool choice with a 400, so `auto` with good descriptions is the right approach.

**D2: Multiple tools.** The model can request several tools in one round. We run them concurrently, return all results in one message in request order, and the model combines them. A chain (for example search → calculator) is another round, up to 5. After that, a final call with `tool_choice: none` forces a text answer.

**D3: Tool errors.** A tool error never crashes the request. It becomes a failed `ToolResult`: the LLM receives it as `is_error: true` and explains it, the client sees `success: false` and `error` in `tools_used`, and it's logged in ToolExecution.

**D4: Security.**
- *Calculator:* an `ast` whitelist, never `eval`/`exec`, with limits on length, exponent and nesting.
- *Database:*
  - A separate `sample.db`, opened **read-only** (`mode=ro` URI) with an **authorizer callback** that allows only `SELECT`, `READ` and `FUNCTION` (needed for `date('now')`), so SQLite rejects every other action: INSERT, UPDATE, DELETE, ATTACH, PRAGMA.
  - Python's `sqlite3` module itself refuses more than one statement per call.
  - A row limit of 100, and a time limit through SQLite's progress handler.
- *All tools:* JSON Schema validation and a timeout.
- *Prompt injection:* tool outputs are treated as data. Search is a mock here, so risk is low.
- *Secrets:* the API key comes from env only.
- *Input:* message length limit.

**D5: Context management.**
- The system prompt and tool list are fixed for the conversation, and history is only appended to.
- Later turns replay the stored user messages plus each turn's tool calls and results (`llm_blocks`), but **not the model's earlier thinking blocks**, and only for `complete` turns.
- Long chats send only the last `MAX_HISTORY_TURNS` (20) turns, cut at turn boundaries so a tool call never loses its result.

Why: current Claude models reject a replayed thinking block if earlier history changed (the "history-editing check"). Dropping all earlier thinking blocks is allowed, and after that, trimming old turns is safe whatever the account age. Within one turn, thinking blocks are passed back unchanged, which tool use requires. Summarizing old turns (REQ-45) is on the "if time" list.

**D6: Model settings.**
- No `thinking` parameter (spec v0.6): Claude Opus 5.5 thinks adaptively by default and can't turn it off, so thinking blocks still arrive and the replay rule above still applies. `effort` is fixed at `medium` in code (explicit, so a changed API default can't change behavior), and `max_tokens` is 16,000.
- Refusals are handled with a plain `stop_reason` check (section 4, step 5). No beta features are used. The API's automatic refusal fallback is possible future work.

**D7: Token tracking (REQ-42).** Sum `input_tokens + output_tokens` over every LLM round in the turn, store it on the assistant message, and return it as `tokens_used`. Prompt caching is not used, so there are no cache token fields to add.

## 9. Requirement coverage

| Requirements | Component(s) |
|---|---|
| REQ-1, 13-16, 21-22, 27-29, 33 | chat service + LLM client + executor + routes |
| REQ-2, 3 | chat service history (D5) + Message storage |
| REQ-4, 17-20 | conversation service + routes + cascade (section 5) |
| REQ-5..9 | one tool file each (section 3.3) |
| REQ-10 | all 5 tools (G4) |
| REQ-11, 12 | tool base + registry + `GET /tools` |
| REQ-23..26 | models + orchestrator logging |
| REQ-30, 41 | executor validation + Pydantic |
| REQ-31, 40 | executor timeout (section 3.2) |
| REQ-32 | round limit (section 4) |
| REQ-34, 35, 36 | stack (section 1) |
| REQ-37 | Dockerfile + compose (section 10) |
| REQ-38 | tests + fake LLM (section 11) |
| REQ-42 | D7 |
| REQ-47..50 | stage 6 |
| REQ-39, 43-46 | **Deferred** ("if time", approved in stage 1) |

## 10. Deployment shape

- **Dockerfile:**
  - `python:3.12-slim`, with dependencies pinned in `requirements.txt` (including `tzdata` and the test tools).
  - It copies `app/` and `tests/`, and runs `mkdir -p /app/data && chown app:app /app/data` before `USER app`, so the non-root user can write to the volume.
  - Uvicorn on port 8000, with a health check on `/health`.
- **docker-compose.yml:**
  - One service, `api`, with port `8000:8000`.
  - `env_file: .env` provides `ANTHROPIC_API_KEY` and `LLM_MODEL`.
  - The named volume `chatbot-data` is mounted at `/app/data`.
- **Tests in Docker:** `docker compose run --rm api pytest`. No API key is needed, because the fake LLM is used.

## 11. Fake LLM (test design)

`tests/fake_llm.py` implements the same `complete(...)` method as the real client:
- **Scripted responses:** each test gives a list of responses, returned one per call. Each response can contain `thinking`, `text` and `tool_use` blocks, any `stop_reason` (`end_turn`, `tool_use`, `refusal`, `max_tokens`, unexpected values), and `usage`.
- **Records every request** it receives (system, messages, tools, tool_choice), so tests can check exactly what was sent. For example:
  - thinking blocks are passed back within a turn and dropped on later turns,
  - all tool results come in one message, in order,
  - `tool_choice: none` is used after the round limit.
- **Can raise SDK errors**, to test the 502 path.

With this, all 6 required tests (S1:348-354) and every failure path can be tested with the same result every run.

## 12. Risks and early checks

| # | Risk | Early check |
|---|---|---|
| R1 | The LLM does math in its head instead of calling the calculator | Manual real-LLM check in the tool-loop task; tune descriptions and D0 |
| R2 | Calculator abuse (eval, huge powers, deep nesting) | Attack-input unit tests (`__import__`, `9**9**9`, long input) |
| R3 | DB tool modifies data or reads app data | Tests that INSERT/DROP/ATTACH/PRAGMA and multiple statements are rejected; separate file |
| R4 | A slow tool blocks the response | Executor test with a deliberately slow fake tool: the response returns in < 1.5 × the timeout |
| R5 | History replay rejected by the API | D5 design; fake-LLM request checks; a real-LLM multi-turn check in stage 5 |
| R6 | Timezones fail in Docker | `tzdata`; a datetime convert check inside the container in the skeleton task |
| R7 | Flaky tests | Fake LLM, fixed seeds, injected clock and seed date, no network |
| R8 | API cost during manual tests | Few manual checks; model switchable via `LLM_MODEL` |
| R9 | ~~`strict: true` may reject some schema features~~ Closed in spec v0.6: `strict` is not used | The executor validates every input itself with `jsonschema` anyway. Spec v0.4: the registry removes the keywords strict mode doesn't support (`maxLength` etc.) from `input_schema`. If the API still rejects a schema, drop `strict` for that tool |
| R10 | Fake LLM drifts from the real response shape | The fake uses the same block types and stop reasons as the SDK, plus one real-LLM smoke check per stage-5 run |
| R11 | Orphan rows after delete/reset | ORM cascade + a test that counts rows after delete and reset |
| R12 | Non-root user can't write the volume | `chown` in the Dockerfile; checked in the skeleton task by starting compose and creating a conversation |

## 13. Decisions taken (2026-11-10)

- **C1: database tool input:** the LLM writes SQL, and the tool runs it read-only (section 3.3, D4). This is a documented deviation from S1:204.
- **C2: limits:** tool timeout 5 s per round, max 5 tool rounds, max 20 history turns, DB row limit 100, message max 10,000 chars, expression max 200 chars, 8 executor workers.
- **C3: refusal fallback beta:** not used (D6). Plain refusal check only.
- **D8: no separate data-access (repository) layer (2026-11-10):** the services call the SQLAlchemy session and `commit()` themselves. At this size a repository layer would add a file per table and no real benefit; the session is still injected, so tests use temp files. Revisit if a second storage backend is ever needed.

## 14. Review log

**Self-review (v1):**

| # | Finding | Fix |
|---|---|---|
| F1 | Tool logging could be lost when the LLM failed | `pending` assistant message, executions logged per round |
| F2 | A failed turn left two user messages in a row | Replay uses only `complete` turns |
| F3 | A date in the system prompt would change daily | D0 |
| F4 | SQLite connections shared across threads; unbounded queries | One connection per call; progress-handler limit |
| F5 | `strict` might reject schemas | R9 |

**Independent review (v2):** 19 findings, all accepted.

| # | Finding | Fix (section) |
|---|---|---|
| 1 | `with ThreadPoolExecutor` would wait for slow tools and defeat the timeout | Module-level pool, `future.result(timeout)`, wall-clock test (3.2, R4) |
| 2 | DB writes from worker threads | Only the orchestrator writes (2, 3.2) |
| 3 | Route style undecided | Plain `def` routes, `check_same_thread=False` (1, 5) |
| 4 | SQLite ignores foreign keys by default | ORM cascade + test (5, R11) |
| 5 | Volume not writable by the non-root user | `chown` in the Dockerfile (10, R12) |
| 6 | Fake LLM too limited | Thinking blocks, all stop reasons, request recording (11) |
| 7 | `sql` input differs from S1 | Documented deviation (3.3, C1) |
| 8 | System prompt combination undefined | D0 |
| 9 | Refusal fallback beta hard to justify | Removed (D6, C3) |
| 10 | Round limit and unknown stop reasons unclear | Rewritten loop with an explicit `else` branch (4) |
| 11 | How pending/error/refusal show in history | Defined (6) |
| 12 | 422 before 404; whitespace-only content | Strip + order fixed (4, 6) |
| 13 | Parallel results in completion order | Request order (3.2) |
| 14 | Seed relative to now; reseeding | Seed date parameter, idempotent (5) |
| 15 | Prompt-cache claim without caching | Removed (D0, D7) |
| 16 | Tests in Docker need a key and the test files | Lazy client; tests copied into the image (2, 10) |
| 17 | `last_message_at` never updated | Set on every save (4, 5) |
| 18 | Multiple-statement wording wrong; authorizer needs FUNCTION | Corrected (D4) |
| 19 | Section order; datetime field checks | Renumbered; per-operation checks (3.3) |
