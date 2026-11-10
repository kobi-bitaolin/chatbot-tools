# Chatbot Tools: Architecture

- **Source (S1):** `chatbot-tool.md`. **Requirements:** `docs/chatbot-requirements.md` (approved 2026-11-10)
- **Stage:** 2, architecture
- **Status:** Draft, awaiting approval
- **Date:** 2026-11-10

Guiding rule: keep it as small as possible and explainable line by line. The design follows the S1 diagram (S1:74-96): Chat API → LLM → Tool Executor → final response.

---

## 1. Stack

| Choice | Proposal | Why | Rejected alternative |
|---|---|---|---|
| Language | **Python 3.12** (Docker image `python:3.12-slim`) | Fixed by S1:341 (3.11+). 3.12 is stable and has good error messages | 3.13: newer, and some libraries lag behind |
| Web framework | **FastAPI** + Uvicorn | Request/response validation through Pydantic models (gives REQ-30 for free at the API layer), automatic `/docs` page for the evaluator, `TestClient` for tests | Flask: no built-in validation or schema; more hand-written code |
| LLM | **Claude via the official `anthropic` Python SDK**, model from env var `LLM_MODEL`, default `claude-opus-5-5` | Native function calling. The SDK gives typed errors and usage counts. The model is configurable, so a cheaper one (`claude-sonnet-5-5`, `claude-haiku-5-5`) is a one-line `.env` change; your decision | LangChain/agent frameworks: they hide the tool loop, and the loop is exactly what the interview asks about (S1:27) |
| Tool loop | **Hand-written loop** (not the SDK's beta Tool Runner) | We need per-call timeouts, logging to the DB, a max-rounds limit, and the exact `tools_used` format. Writing the loop yourself shows you understand function calling | SDK Tool Runner: less code, but a beta and a "black box" for the interview |
| App storage | **SQLite + SQLAlchemy 2.0**, file on a Docker volume | Zero setup, one file, survives restarts (G10). SQLAlchemy models map 1:1 to the S1 data model | PostgreSQL: one more container and more setup, with no benefit at this size |
| Sample data (DB tool) | **Separate SQLite file** `sample.db` (products, users, orders), seeded on startup | Kept apart from app data, so the tool can never touch conversations (security) | Same DB file: the tool could read or damage app tables |
| Tests | **pytest** + FastAPI `TestClient` + a **fake LLM** | Repeatable, free, no network. The fake replays scripted responses, including tool calls | Calling the real LLM in tests: flaky, costs money, needs a key |
| Config | **pydantic-settings** reading env vars; `.env.example` documents them | Rule: no secrets in the repo | Hard-coded config |

## 2. Components

| Component | File | Responsibility |
|---|---|---|
| API routes | `app/api/routes.py` | HTTP only: parse the request, call a service, return a response, map errors to status codes. No business rules |
| Schemas | `app/schemas.py` | Pydantic request/response models in the S1 formats |
| Conversation service | `app/services/conversations.py` | Create / list / get / delete / reset conversations |
| Chat service (orchestrator) | `app/services/chat.py` | The tool loop (section 4): history → LLM → tools → LLM → final answer; saves messages, token counts, executions |
| LLM client | `app/llm/client.py` | Thin wrapper around the Anthropic SDK with one method, `complete(system, messages, tools)`. The fake LLM in tests implements the same method |
| Tool base | `app/tools/base.py` | Shared tool shape (section 3) |
| Tool registry | `app/tools/registry.py` | Holds all tools; gives definitions to the LLM and to `GET /tools` |
| Tool executor | `app/tools/executor.py` | Validates input against the schema, runs tools in parallel with a timeout, measures time, catches errors, returns `ToolResult`s. Never raises |
| Tools | `app/tools/calculator.py`, `web_search.py`, `weather.py`, `database.py`, `datetime_tool.py` | One file per tool, pure logic, easy to unit test |
| Storage | `app/db.py`, `app/models.py` | Engine/session, ORM models (section 5) |
| Sample DB | `app/sample_data.py` | Creates and seeds `sample.db` with deterministic data |
| Config | `app/config.py` | Settings: API key, model, effort, timeouts, limits, DB paths |

Business rules live in services and tools, so unit tests don't need HTTP.

## 3. Tool interface

Every tool is a small class with the same shape:

```python
class Tool:
    name: str                    # "calculator"
    description: str             # tells the LLM when to use it (this drives tool selection, D1)
    parameters: dict             # JSON Schema, exactly the S1:102-119 format
    def run(self, **kwargs) -> dict   # returns the "output" dict, or raises ToolError
```

The executor wraps every run into a `ToolResult` in the S1:121-131 format, extended with `error` (G3):

```json
{"tool": "calculator", "input": {"expression": "1/0"}, "output": null,
 "success": false, "error": "Division by zero", "execution_time_ms": 1}
```

Format translation: S1 uses `parameters`, while the Anthropic API calls the same JSON Schema `input_schema`. The registry stores the S1 format and converts it in one place when sending to the LLM. Each definition sets `strict: true` and `additionalProperties: false`, so the model's arguments always match the schema.

**Tool details**

| Tool | Input | Output | Notes |
|---|---|---|---|
| calculator | `expression: str` (max 200 chars) | `{"result": float}` | **Safe parser, no `eval`**: parse with Python's `ast` module and allow only numbers, + − × ÷ % `**`, parentheses, and a whitelist of `math` functions/constants (sqrt, sin, cos, tan, log, exp, pi, e...). `^` is converted to `**` (S1:179). Limits on exponent size and nesting stop `9**9**9`-style attacks. Errors: invalid expression, division by zero, result too large |
| web_search | `query: str` | `{"results": [{title, snippet, url}]}` | Mock: a small dict of predefined results, matched by keywords. No match returns an empty list (not an error) |
| weather | `location: str` | `{"location", "temperature", "condition", "humidity"}` | Mock: realistic random values. The random generator is injected, so tests can fix it |
| database_query | `sql: str` (a single SELECT) | `{"columns": [...], "rows": [...], "row_count": n}` | The LLM turns the user's natural-language question into SQL. The tool definition includes the table schemas so it knows the columns. Dates such as "last month" use SQLite's own `date('now', ...)`. Each call opens its own read-only connection, because SQLite connections can't be shared across threads. Security in D4. See open choice C1 |
| datetime | `operation: "current" \| "convert" \| "calculate"`, plus `timezone`, `datetime`, `from_tz`, `to_tz`, `days`/`hours`/`minutes` as needed | `{"result": "2026-11-10T14:30:00+02:00", ...}` | Uses Python `zoneinfo`. **The Docker image needs the `tzdata` package** (slim images have no timezone database, R6). The clock is injected, so tests are repeatable |

## 4. Orchestration loop (the core)

One user message = one "turn". Inside a turn there can be several LLM **rounds**.

```
POST /conversations/{id}/messages {"content": "..."}
 1. Load the conversation (404 if missing). Validate that content is non-empty (422).
 2. Save the user message, and create the assistant message right away with
    status "pending", so every tool execution can be logged against it immediately.
 3. Build the LLM input: the conversation's system prompt + history (see D5) + the new message.
 4. round = 1
 5. Call the LLM with all tool definitions (tool_choice: auto).
 6. Add this round's token usage to the turn total.
 7. If stop_reason == "tool_use":
      a. Run ALL requested tool calls in parallel through the executor (timeout each).
      b. Log every call as a ToolExecution row.
      c. Send ALL results back in ONE user message (tool_result blocks;
         failures marked is_error: true with the error text).
      d. round += 1. If round > MAX_TOOL_ROUNDS (5): make one last call with
         tool_choice "none", so the LLM must answer in text with what it has (D2, REQ-32).
      e. Go to 5.
 8. If stop_reason == "end_turn": take the text and complete the assistant message
    (content, tools_used, tokens_used, the raw LLM blocks for later replay, status "complete").
 9. If stop_reason == "refusal" or "max_tokens": save and return a short, honest fallback message.
10. Return {message, tools_used, tokens_used}.
```

**Failure paths**

| What fails | What happens | Requirement |
|---|---|---|
| Tool raises an error | Executor catches it → `success: false` + error text → sent to the LLM as `is_error: true` → the LLM tells the user politely | REQ-28 |
| Invalid tool parameters | Executor validates against the JSON Schema before running → validation error returned the same way | REQ-30 |
| Tool times out | That call becomes `success: false, error: "Timed out after 5s"`. Other calls in the same round keep their results (partial results, G9) | REQ-31 |
| Unknown tool name | Error result "Unknown tool", same path | REQ-30 |
| LLM keeps calling tools | Stops after 5 rounds and forces a text answer | REQ-32 |
| LLM API error (network, 429, 5xx) | The SDK retries automatically (2 retries). Still failing → HTTP 502 with a clear message. The assistant message gets status "error" with the error text. Tool executions already run stay logged. Later turns skip this failed turn when building history, so the LLM never sees two user messages in a row | robustness, REQ-26 |
| Conversation not found | 404 | REQ-19/20 |

Why all results go back in one message: the Claude docs say that splitting parallel tool results across several messages teaches the model to stop making parallel calls. That matters for "multiple tools" (REQ-29).

## 5. Data model

Two SQLite files: `app.db` (below) and `sample.db` (tool data).

**Conversation**: `id` (str, `conv_` + random, G12), `system_prompt` (text, nullable), `created_at`, `last_message_at` (nullable). Deleting a conversation deletes its messages and executions (cascade). Reset deletes messages and executions but keeps the conversation (G1).

**Message**: `id`, `conversation_id` (FK), `role` (`user` / `assistant`), `content` (text), `tools_used` (JSON, nullable), `tokens_used` (int, nullable), `llm_blocks` (JSON, nullable, assistant only), `status` (`pending` / `complete` / `error`, assistant only), `created_at`.
- The system prompt lives on the Conversation, not as a message row (G13). S1 lists `system` as a role (S1:296); it stays allowed in the model but isn't used.
- `llm_blocks` is an **addition** to S1: the raw assistant/tool blocks of the turn, stored so later turns can replay what the tools returned (D5). It's not shown in the API.

**ToolExecution**: `id`, `message_id` (FK to the assistant message of that turn), `tool_name`, `input` (JSON), `output` (JSON, nullable), `success` (bool), `error_message` (nullable), `execution_time_ms` (int), `created_at`.
- The assistant message is created at the start of the turn (`pending`), so each execution is saved the moment it finishes, linked to that message (S1:303). Nothing is buffered, and nothing is lost if the LLM fails mid-turn (REQ-26).
- `status` is an **addition** to S1. History replay uses only `complete` turns.

**Sample DB** (`sample.db`, seeded deterministically on startup): `users` (~50), `products` (~30), `orders` (~500 spread over the last 12 months relative to the current date, so "last month" always has data), `order_items`.

## 6. Endpoints

| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| POST | `/conversations` | `{"system_prompt"?: str}` | 201 `{id, created_at}` | 422 |
| GET | `/conversations` | none | 200 `{"conversations": [{id, created_at, last_message_at, message_count}]}` | none |
| GET | `/conversations/{id}` | none | 200 `{id, system_prompt, messages: [{role, content, tools_used?, tokens_used?, created_at}], created_at}` | 404 |
| DELETE | `/conversations/{id}` | none | 204 | 404 |
| POST | `/conversations/{id}/reset` | none | 200 `{id, message_count: 0}` | 404 |
| POST | `/conversations/{id}/messages` | `{"content": str}` (1-10,000 chars) | 200 `{message: {role, content}, tools_used: [...], tokens_used}` | 404, 422, 502 |
| GET | `/tools` | none | 200 `{"tools": [{name, description, parameters}]}` | none |
| GET | `/health` | none | 200 `{"status": "ok"}` | none (used by Docker) |

`/health` is an addition for the Docker health check. `parameters` in `GET /tools` is an addition to S1:270-280 so the evaluator sees each tool's inputs.

## 7. Folder structure

```
chatbot-tools/
├── app/
│   ├── main.py            # creates the FastAPI app, startup (create tables, seed sample.db)
│   ├── config.py
│   ├── db.py  models.py  schemas.py  sample_data.py
│   ├── api/routes.py
│   ├── services/conversations.py  chat.py
│   ├── llm/client.py
│   └── tools/base.py  registry.py  executor.py
│       calculator.py  web_search.py  weather.py  database.py  datetime_tool.py
├── tests/
│   ├── conftest.py        # temp DBs, TestClient, fake LLM fixture
│   ├── fake_llm.py
│   ├── test_tools_*.py    # unit tests per tool
│   ├── test_executor.py
│   └── test_api_*.py      # integration: chat, history, logging, errors
├── docs/                  # stage documents
├── Dockerfile  docker-compose.yml  requirements.txt  .env.example
├── README.md  AI_USAGE.md
└── .gitignore  .gitattributes
```

## 8. Key decisions (for the README, S1:313-321)

**D0: The system prompt never contains changing values** (such as today's date). It stays byte-identical for the whole conversation, which keeps replay valid (D5) and the prompt cache warm. The LLM gets the date from the datetime tool or from SQL `date('now')`.

**D1: Tool selection.** The LLM decides, using the tool descriptions. Each description says what the tool does and when to use it, for example: "Use for any arithmetic; never calculate in your head." `tool_choice` is `auto`. The system prompt adds: "Use a tool whenever it can give a more accurate answer than you can." Note: the current Claude Opus/Sonnet models reject *forced* tool choice (`any` / a named tool) with a 400, so `auto` with good descriptions is also the only option.

**D2: Multiple tools.** The model may request several tools in one round (parallel calls). We run them concurrently in a thread pool, return all results in one message, and let the model combine them. If a result leads to another tool (for example search → calculator), it's another round, up to 5 rounds. After that, a final call with `tool_choice: none` forces a text answer.

**D3: Tool errors.** A tool error never crashes the request. The executor turns it into a failed `ToolResult`, which the LLM receives as `is_error: true`, and the LLM explains the problem to the user. The client sees it in `tools_used` (`success: false`, `error`), and it's logged in ToolExecution.

**D4: Security.**
- *Calculator:* an `ast` whitelist parser, never `eval`/`exec`. Limits on length, exponent size and nesting.
- *Database:* a separate `sample.db`, opened **read-only** (SQLite `mode=ro`) with an **authorizer callback** that allows only reading. INSERT, UPDATE, DELETE, ATTACH, PRAGMA and multiple statements are all rejected by SQLite itself, not by fragile string checks. There's also a row limit (100), and a time limit set through SQLite's progress handler, which aborts long queries.
- *All tools:* strict JSON Schema validation and a timeout.
- *Prompt injection:* tool outputs are data. Search results are mocks here, so risk is low.
- *Secrets:* the API key comes from env only.
- *Input:* message length limit.

**D5: Context management.**
- The system prompt and tool list are fixed for the whole conversation, and history is only appended to.
- Each later turn replays the stored user messages plus each turn's tool calls and results (from `llm_blocks`), but **not the model's earlier "thinking" blocks**.
- For long chats, only the last `MAX_HISTORY_TURNS` (20) turns are sent, cut at turn boundaries so a tool call is never separated from its result.

Why: current Claude models check that a replayed thinking block's history is unchanged and reject edits with a 400 (the "history-editing check"). The API docs allow dropping all earlier thinking blocks. Once those are dropped, trimming old turns is safe, and the design works whatever the account age. Within a single turn, the thinking blocks *are* passed back unchanged, which tool use requires. A better approach (summarizing old turns, Nice item REQ-45) is on the "if time" list.

**D6: Model settings.** Adaptive thinking (the default on Claude Opus 5.5) with `effort` set explicitly from env (`LLM_EFFORT`, default `medium`). `max_tokens` is 16,000 (non-streaming).
- **Refusals:** the code checks for `stop_reason: "refusal"` and returns a clear message.
- **Fallback:** the Claude docs recommend turning on the API's automatic fallback for refusals (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`). It's on by default, can be turned off in config, and is the only beta feature used.

**D7: Token tracking (REQ-42).** Sum `input_tokens + output_tokens` over every LLM round in the turn, store it on the assistant Message, and return it as `tokens_used`.

## 9. Requirement coverage

| Requirements | Component(s) |
|---|---|
| REQ-1, 13-16, 21-22, 27-29, 33 | chat service + LLM client + executor + routes |
| REQ-2, 3 | chat service history building (D5) + Message storage |
| REQ-4, 17-20 | conversation service + routes |
| REQ-5..9 | one tool file each |
| REQ-10 | all 5 tools (G4) |
| REQ-11, 12 | tool base + registry + `GET /tools` |
| REQ-23..26 | models + chat service logging |
| REQ-30, 41 | executor schema validation + Pydantic at the API |
| REQ-31, 40 | executor timeout |
| REQ-32 | MAX_TOOL_ROUNDS in chat service |
| REQ-34, 35, 36 | stack (section 1) |
| REQ-37 | Dockerfile + compose (section 10) |
| REQ-38 | tests/ + fake LLM (stage 3 maps each to ACs) |
| REQ-42 | D7 |
| REQ-47..50 | stage 6 (README, AI_USAGE.md, layout) |
| REQ-39, 43-46 | **Deferred** ("if time", approved in stage 1) |

Every in-scope requirement has a component.

## 10. Deployment shape

- **Dockerfile:**
  - `python:3.12-slim`, with dependencies pinned in `requirements.txt`, which includes `tzdata`.
  - Runs as a non-root user, with Uvicorn on port 8000.
  - Has a health check on `/health`.
- **docker-compose.yml:**
  - One service, `api`, with port `8000:8000`.
  - `env_file: .env` provides `ANTHROPIC_API_KEY`, `LLM_MODEL` and `LLM_EFFORT`.
  - The named volume `chatbot-data` is mounted at `/app/data`, where both DB files live.
- **Tests in Docker:** `docker compose run --rm api pytest`.

## 11. Risks and early checks

| # | Risk | Early check |
|---|---|---|
| R1 | The LLM answers math in its head instead of calling the calculator | Manual real-LLM check in the tool-loop task; tune descriptions and the system prompt |
| R2 | Calculator could be abused (eval, huge powers) | Unit tests with attack inputs (`__import__`, `9**9**9`, very long input) in the calculator task |
| R3 | The DB tool could modify data or read app data | Tests that INSERT/DROP/ATTACH/PRAGMA are rejected; separate file |
| R4 | A stuck tool blocks the request | Executor timeout test with a deliberately slow fake tool. Note: Python can't kill a thread, so the slow call finishes in the background, but the response doesn't wait for it |
| R5 | History replay rejected by the API (history-editing check) | D5 design. A real-LLM multi-turn check with tools in stage 5 |
| R6 | Timezones fail inside Docker (no tz database) | `tzdata` in requirements. A datetime convert check inside the container in the skeleton task |
| R7 | Flaky tests | Fake LLM, fixed random seed, injected clock; no network in tests |
| R8 | API cost during manual testing | Manual checks are few. The model is switchable via `LLM_MODEL` |
| R9 | `strict: true` may not accept every JSON Schema feature (for example optional fields in the datetime tool) | The executor still validates every input itself with the `jsonschema` library, so correctness doesn't depend on strict mode. If the API rejects a schema, drop `strict` for that tool |
| R10 | The fake LLM drifts from the real response shape | The fake returns the same block types as the SDK (`text`, `tool_use`, `stop_reason`, `usage`). One real-LLM smoke check per stage-5 run |

## 13. Review log (self-review, 2026-11-10)

I checked the draft against the requirements, the S1 formats, and the current Claude API documentation:

| # | Finding | Fix |
|---|---|---|
| F1 | Contradiction: one place said "no assistant message on LLM failure", another said "placeholder message", so logging could be lost | The assistant message is created as `pending` at the start of the turn, and executions are logged immediately (sections 4 and 5) |
| F2 | A failed turn would leave two user messages in a row in the history | Replay uses only `complete` turns |
| F3 | Putting the current date in the system prompt would change it every day, breaking replay and caching | D0: no changing values in the system prompt |
| F4 | SQLite connections can't be shared across the executor's threads, and long queries weren't bounded | One connection per call, plus a progress-handler time limit |
| F5 | `strict: true` might reject some schemas | R9: own validation with `jsonschema` regardless |
| Verified | Forced `tool_choice` returns 400 on current Claude models; `auto`/`none` work; parallel results go in one message; failures use `is_error: true`; history-editing check rules (D5) | Matches the design |

## 12. Open choices for the user

- **C1: database tool input.** (a) The LLM writes SQL and the tool runs it read-only, as designed above. Flexible, and it answers any natural-language question. (b) Structured input: the LLM picks a table, filters and an aggregate from fixed options. Safest, but less flexible. **Recommendation: (a)**, because SQLite's own read-only mode and authorizer make it safe, and it's a strong security answer for the interview.
- **C2: limits.** Tool timeout 5 s, max tool rounds 5, max history 20 turns, DB row limit 100, message max 10,000 chars, calculator expression max 200 chars. **Recommendation: accept.**
- **C3: refusal fallback (beta).** On by default, as the Claude docs recommend. **Recommendation: keep it on.**
