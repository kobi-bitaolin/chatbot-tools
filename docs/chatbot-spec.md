# Chatbot Tools: Specification and Test Plan

| | |
|---|---|
| **Version** | 0.7 |
| **Status** | Approved (2026-11-10) |
| **Date** | 2026-11-10 |

## 1. Source documents

| ID | Document |
|---|---|
| S1 | `chatbot-tool.md` (the assignment) |
| S2 | `docs/chatbot-requirements.md` (approved 2026-11-10) |
| S3 | `docs/chatbot-architecture.md` v2 (approved 2026-11-10) |

## 2. Summary and scope

A FastAPI chatbot API where the LLM (Google Gemini) decides when to call 5 tools (calculator, web search, weather, database query, date/time), with conversation management, tool execution logging and Docker.

- **In scope:** all Must items of S1, plus tool timeouts, input validation and token tracking (S2 §7 Q1).
- **Out of scope for now ("if time"):** streaming (REQ-39), custom tool registration, analytics, summarization, rate limiting (REQ-43..46), a real weather API. A UI and authentication are out of scope entirely (S2 §4).

**Glossary**
- **Turn:** one user message and its final assistant answer.
- **Round:** one LLM call inside a turn.
- **Tool round:** a round in which the LLM requested tools and we ran them.
- **Fake LLM:** the scripted test double in S3 §11.

## 3. Functional requirements

Priority: **M** = Must (S1:339-354), **S** = Should included in scope (S2 Q1).

### Conversations
| ID | Requirement | P | Source |
|---|---|---|---|
| FR-1 | `POST /conversations` with an optional `system_prompt` must create a conversation and return 201 `{id, created_at}`. `id` must be `conv_` + 12 lowercase hex characters. `system_prompt` is stripped; an empty or spaces-only value is stored as null (the default is used) | M | S1:243-254, G12 |
| FR-2 | `GET /conversations` must return every conversation as `{id, created_at, last_message_at, message_count}`, ordered by `created_at` descending (newest first) | M | S1:68, G1 |
| FR-3 | `GET /conversations/{id}` must return `{id, system_prompt, created_at, messages}`. Messages are ordered by their database id (insertion order, never tied). Each message has `role`, `content` and `created_at`. Assistant messages also have `status`, `tools_used` and `tokens_used`. Messages with status `error` are shown | M | S1:256-268, S3 §6 |
| FR-4 | `DELETE /conversations/{id}` must return 204 and remove the conversation, its messages and its tool executions | M | S1:70, G1, S3 §5 |
| FR-5 | `POST /conversations/{id}/reset` must remove all messages and tool executions, keep the conversation and its system prompt, and return 200 `{id, message_count: 0}` | M | S1:43, G1 |
| FR-6 | An unknown conversation id must return 404 on GET, DELETE, reset and send | M | S3 §4 |
| FR-7 | Every saved message must set the conversation's `last_message_at` | M | S1:292, S3 §5 |

### Chat and tool loop
| ID | Requirement | P | Source |
|---|---|---|---|
| FR-8 | `POST /conversations/{id}/messages` with `{"content"}` must return 200 `{message: {role: "assistant", content}, tools_used: [...], tokens_used}` | M | S1:142-164, S1:225-241, G2 |
| FR-9 | `content` must be stripped of surrounding spaces and be 1-10,000 characters, otherwise 422. Body validation happens before the 404 check | M | S3 §4, §6 |
| FR-10 | Every LLM call must include all 5 tool definitions with tool choice `auto` (Gemini function-calling mode `AUTO`), except the final call in FR-15. The LLM decides whether to use tools | M | S1:60, D1 |
| FR-11 | When the LLM answers without tools, the API must return its text with `tools_used: []` after exactly one LLM call | M | S1:327 |
| FR-12 | When the LLM requests tools, the system must run them, send the results back, and repeat until the LLM gives a final answer | M | S1:59-63 |
| FR-13 | All tool calls of one round must run, and their results must go back to the LLM in **one** user message, **in the order the LLM requested them**. `tools_used` must use the same order | M | S1:329, D2, S3 §3.2 |
| FR-14 | Each `tools_used` item must be `{tool, input, output, success, error, execution_time_ms}`. `output` is null and `error` is text on failure; `output` is set and `error` is null on success | M | S1:121-131, G3 |
| FR-15 | After 5 tool rounds, if the LLM requests tools again, those calls must not run. Each must get the error result "Tool call limit reached" (`success: false`, `execution_time_ms: 0`), be included in `tools_used` and logged as a ToolExecution, and one final LLM call must be made with tool choice `none` (Gemini mode `NONE`) | M | S1:332, S3 §4 |
| FR-16 | A tool error, an invalid input, an unknown tool name or a timeout must never fail the request. The result must go to the LLM with `is_error: true` and the error text | M | S1:328, S1:330, D3 |
| FR-17 | Tool input must be validated against the tool's JSON Schema, plus the per-operation datetime checks, before running. A failure gives an error result starting with "Invalid input:" | S | S1:330, S1:360 |
| FR-18 | The tools of one round share a deadline of `TOOL_TIMEOUT_S` (default 5). A call still running at the deadline gets the error "Timed out after {N}s", where N is formatted with Python's `{:g}` (5.0 → "5", 0.5 → "0.5"). Other calls in the round keep their results | S | S1:331, S1:359, G9 |
| FR-19 | `tokens_used` must be the sum of `input_tokens + output_tokens` over all LLM calls of the turn, stored on the assistant message | S | S1:162, S1:361, D7 |
| FR-20 | The first message of a new or reset conversation must be sent to the LLM as the only message | M | S1:333 |

### History and context
| ID | Requirement | P | Source |
|---|---|---|---|
| FR-21 | **Replay rule.** Each LLM call sends the history of `complete` turns, then the new user message. Each earlier turn is replayed as: (1) the user message text; (2) for each tool round, the assistant blocks (`text` and `tool_use`, thinking removed) and the user message with the `tool_result` blocks, all taken from `llm_blocks`; (3) the final answer as one assistant text message, taken from `Message.content`. This rule is the same for every outcome (`end_turn`, `refusal`, `max_tokens`) | M | S1:41-42, D5 |
| FR-22 | `llm_blocks` stores all of the turn's blocks exactly as received, thinking included. Thinking blocks are passed back unchanged within the turn, and removed only when building replay for later turns | M | D5 |
| FR-23 | Only the last 20 complete turns (`MAX_HISTORY_TURNS`) may be sent. The cut is at a turn boundary, so the first message sent is always a user message | M | S1:321, D5 |
| FR-24 | The system prompt sent must be `APP_INSTRUCTIONS + "\n\n" + (system_prompt or "You are a helpful assistant.")`, and byte-identical on every call of the conversation. `APP_INSTRUCTIONS` is fixed text plus the registered tool names in registry order (NFR-12) | M | S1:247, D0 |

### LLM outcomes
| ID | Requirement | P | Source |
|---|---|---|---|
| FR-25 | If an LLM call fails, the LLM layer raises its own `LLMUnavailableError`: for any Gemini SDK error (`google.genai.errors.APIError`, i.e. an HTTP error such as 429 or 5xx after the SDK's retries), a connection or timeout error, or a call that can't be made at all (no `GEMINI_API_KEY` configured). The service catches only `LLMUnavailableError`, and the API must return 502 `{"detail": "LLM service unavailable"}`. The assistant message gets status `error` and content "LLM service unavailable". Tool executions already run stay logged. The original error is written to the server log | M | S3 §4 |
| FR-26 | `stop_reason` handling (the internal stop reason from FR-37): `end_turn` → content = the text blocks joined (status `complete`). `refusal` → content "I can't help with that request." (status `complete`). `max_tokens` → the text so far + " [response cut off]" (status `complete`). Any other value → 502 `{"detail": "Unexpected LLM response"}`, with status `error` and content "Unexpected LLM response" | M | S3 §4 step 5 |

### Tools
| ID | Requirement | P | Source |
|---|---|---|---|
| FR-27 | **Calculator** evaluates `expression` safely (an `ast` whitelist, `^` = power) and returns `{"result": float}`. **All numbers are converted to float**, and after every operation and function call a result that isn't finite (inf/nan) gives "Result too large", as does `OverflowError`. Errors: "Invalid expression" (syntax, a non-whitelisted node or name, a wrong argument count, math domain errors such as `sqrt(-1)` or `log(0)`), "Division by zero", "Exponent too large" (absolute exponent > 1000), "Result too large" | M | S1:170-181, D4 |
| FR-28 | **Web search** (mock) returns `{"results": [{title, snippet, url}]}` for queries that match predefined keywords, and `{"results": []}` otherwise | M | S1:183-190, G5 |
| FR-29 | **Weather** (mock) returns `{location, temperature (°C, integer -30..45), condition (one of sunny/cloudy/rainy/snowy/windy/foggy), humidity (integer 0..100)}`, from an injectable random generator | M | S1:192-199 |
| FR-30 | **Database query** runs one read-only SELECT on `sample.db` and returns `{columns, rows, row_count, truncated}`. It returns at most 100 rows. `row_count` is the number of rows returned, and `truncated` is true if more exist | M | S1:201-208, C1, D4 |
| FR-31 | **Date/time** supports `current` (optional `timezone`, default UTC), `convert` (`datetime`, `from_tz`, `to_tz`) and `calculate` (`datetime` + at least one of `days`/`hours`/`minutes`, which may be negative). The output is `{"result": "<ISO 8601>"}` only: with offset when a timezone is known (`current`, `convert`, or a `calculate` input that has an offset), without offset for a `calculate` input without one. For `convert`, `datetime` must have no offset (`from_tz` defines it); an input with an offset gives "Invalid input: datetime must not include an offset for convert". Unknown timezone → "Unknown timezone: X" | M | S1:210-219 |
| FR-32 | `GET /tools` must return `{"tools": [{name, description, parameters}]}` for all 5 tools, with `parameters` in the S1:102-119 format | M | S1:270-280 |
| FR-33 | Tool definitions are given to the LLM layer as `{name, description, input_schema}` (internal format), where `input_schema` is the tool's S1 `parameters` unchanged (limits such as `maxLength` included). The LLM layer sends each one as a Gemini function declaration `{name, description, parameters_json_schema}` with that same schema. The executor validates every input against the same schema (FR-17) | M | S1:102-119, S3 §3.1 |
| FR-36 | Every LLM request must use Gemini's `generate_content`, `model` = `LLM_MODEL` (default `gemini-3.1-flash-lite`), `max_output_tokens` 16,000 and the system prompt as `system_instruction`. No thinking settings are sent (the model's default applies; any thought parts are still handled by FR-21/FR-22). Tools are sent as declarations only, so the SDK never runs a function itself (the app's tool loop does) | M | D6 |
| FR-37 | **Internal LLM format and translation.** The chat service speaks one internal format, and only `app/llm` knows Gemini's. Internal messages are `{role: user|assistant, content: text or [blocks]}` with block types `text`, `thinking`, `tool_use {id, name, input}` and `tool_result {tool_use_id, content, is_error?}`. **Out (to Gemini):** role `assistant` → `model`; `text` → text part; `thinking` → thought part; `tool_use` → `function_call` part with the same `id`; the `tool_result` blocks of a round → `function_response` parts in **one** `user` Content, each with the call's `id` and `name` and `response` `{"result": ...}` (or `{"error": ...}` when `is_error`). A `thought_signature` received on a part is stored on its block and sent back on the same part unchanged. **In (from Gemini):** parts → blocks the same way. `stop_reason`: any `function_call` part → `tool_use`; finish reason `STOP` → `end_turn`; `MAX_TOKENS` → `max_tokens`; `SAFETY`, `PROHIBITED_CONTENT`, `BLOCKLIST`, `SPII` or a blocked prompt → `refusal`; any other value → its name unchanged (FR-26: unexpected). Tokens: `input_tokens` = `prompt_token_count`, `output_tokens` = `candidates_token_count` + `thoughts_token_count` (missing counts are 0) | M | S1:30, D9 |

### Logging and health
| ID | Requirement | P | Source |
|---|---|---|---|
| FR-34 | Every tool call (success, failure, timeout, limit) must be saved as a ToolExecution row `{message_id, tool_name, input, output, success, error_message, execution_time_ms, created_at}`, linked to the turn's assistant message, and saved right after its round | M | S1:302-309, S1:346 |
| FR-35 | `GET /health` must return 200 `{"status": "ok"}` | M | S3 §6 |

## 4. Non-functional requirements

| ID | Category | Requirement | Source |
|---|---|---|---|
| NFR-1 | Platform | The app runs on Python 3.12 (meets 3.11+) | S1:341 |
| NFR-2 | Deployment | From a clean clone with `.env` set, `docker compose up --build` serves `/health` within 60 s, and the non-root container user can write to `/app/data` | S1:347, R12 |
| NFR-3 | Deployment | `docker compose run --rm api pytest` passes with no `GEMINI_API_KEY` set | S3 §10 |
| NFR-4 | Persistence | Conversations and messages survive an app restart (same data files) | G10 |
| NFR-5 | Security | The calculator never runs `eval`/`exec`. Names, attributes, calls to non-whitelisted functions, and expressions over 200 characters are rejected | S1:320, D4 |
| NFR-6 | Security | The database tool can't change data or read app data. INSERT/UPDATE/DELETE/DROP/CREATE/ATTACH/PRAGMA and multiple statements are rejected, and a query running past 2 s is aborted | S1:320, D4 |
| NFR-7 | Security | No secrets in the repo: `.env` is git-ignored, and `.env.example` lists every variable without values | rule 11 |
| NFR-8 | Performance | When a tool hangs, the response returns within 1.5 × `TOOL_TIMEOUT_S` plus the LLM time | R4 |
| NFR-9 | Testability | Automated tests use no network and no API key, and give the same result on every run (fake LLM, fixed seeds, injected clock and seed date) | S1:348, R7 |
| NFR-10 | Data | Sample data is seeded only when `sample.db` doesn't exist, and the same seed date always gives identical data. Orders cover the 12 months before the seed date | S3 §5 |
| NFR-11 | Submission | The repo has README.md (the 6 sections of S1:389-395 plus decisions D1-D5 and the SQL deviation), AI_USAGE.md (the S1:399-413 template), Dockerfile, docker-compose.yml, requirements.txt, code and tests | S1:374-413 |
| NFR-12 | Maintainability (REQ-51) | Separation of concerns: each layer of architecture §2.1 has one job, and imports go one way only (api → services → tools / llm / models). Tools import only the standard library, `jsonschema` and `app.tools`; services never import `fastapi` or `google.genai`; only `app/llm` imports `google.genai`, and it doesn't import `app.config`; the routes don't import `sqlalchemy` (except the `Session` type) or `app.models`. The chat service never sees SDK objects or SDK errors (it gets an `LLMResult` or an `LLMUnavailableError`), and the tool names in the system prompt come from the registry | S1:30 ("well-structured") |

## 5. Data rules

| Entity.field | Type | Required | Rule |
|---|---|---|---|
| Conversation.id | str | yes | `^conv_[0-9a-f]{12}$`, unique |
| Conversation.system_prompt | text | no | stripped; empty → null; ≤ 4,000 chars (422 otherwise) |
| Conversation.created_at / last_message_at | datetime UTC | yes / no | ISO 8601 in the API |
| Message.role | str | yes | `user` or `assistant` (`system` allowed, not used) |
| Message.content | text | yes | user: 1-10,000 chars after stripping. Assistant: the final answer (FR-26), "" while pending, or the error text (FR-25/26) |
| Message.status | str | assistant only | `pending` / `complete` / `error` |
| Message.tools_used | JSON | no | list of FR-14 items |
| Message.tokens_used | int | no | ≥ 0 |
| Message.llm_blocks | JSON | no | a list of the turn's messages after the user message, exactly as sent and received: `[{role: "assistant", content: [blocks incl. thinking]}, {role: "user", content: [tool_result blocks]}, ..., {role: "assistant", content: [final blocks]}]`. Not exposed in the API. Replay follows FR-21 |
| ToolExecution.tool_name | str | yes | one of the 5 tool names, or the name the LLM sent (unknown tool) |
| ToolExecution.input / output | JSON | yes / no | |
| ToolExecution.success | bool | yes | |
| ToolExecution.error_message | text | no | set exactly when success is false |
| ToolExecution.execution_time_ms | int | yes | ≥ 0 |

## 6. Tool contracts

`parameters` for each tool (S1 format). The descriptions are drafts; R1 tuning may adjust the wording.

| Tool | Description (draft) | parameters |
|---|---|---|
| `calculator` | "Evaluate a math expression. Use for ANY arithmetic, percentages or math functions, even trivial ones or ones you think have no answer (such as division by zero): the tool reports the error. Never calculate in your head." | `expression: string (maxLength 200)`, required |
| `web_search` | "Search the web for current information. Returns titles, snippets and URLs." | `query: string (maxLength 300)`, required |
| `weather` | "Get the current weather for a location." | `location: string (maxLength 100)`, required |
| `database_query` | "Run ONE read-only SQLite SELECT on the store database. Tables: users(id, name, email, country, created_at), products(id, name, category, price), orders(id, user_id, order_date, status, total), order_items(id, order_id, product_id, quantity, unit_price). Use date('now', ...) for relative dates." | `sql: string (maxLength 2000)`, required |
| `datetime` | "Current date/time, timezone conversion, or adding/subtracting time. Timezones are IANA names like Europe/London." | `operation: enum[current, convert, calculate]` (required), `timezone`, `datetime` (ISO 8601), `from_tz`, `to_tz`: strings; `days`, `hours`, `minutes`: integers |

## 7. Assumptions and decisions

- **Assumptions:**
  - A1: a single client, with no authentication.
  - A2: mock data is acceptable (S1:52-53).
  - A3: Gemini requires each `thought_signature` to come back on its original part (needed for function calling on Gemini 3), so FR-37 keeps it on the block.
- **Decisions:** D0-D7 and C1-C3 in S3 §8 and §13. G1-G15 in S2 §5.

## 8. Open questions

None.

## 9. Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-11-10 | First draft from S1-S3 |
| 0.2 | 2026-11-10 | Independent review, 17 findings applied: calculator float/finite checks and domain errors (FR-27); exact error strings (FR-25, FR-26); replay rule and `llm_blocks` structure (FR-21, FR-22); round-limit entries logged (FR-15); timeout formatting (FR-18); ordering by id/clock (FR-2, FR-3); datetime output and offsets (FR-31); `row_count` (FR-30); empty system_prompt (FR-1); FR-36 model settings; reworked AC-15, 19, 20, 26, 27, 30, 32, 36, 37, 39, 41, 43, 46, 47; added AC-57 |
| 0.3 | 2026-11-10 | Q5 (found in the T-3 Docker smoke test, approved by the user): FR-25 also covers an LLM call that can't be made (no API key → SDK `TypeError`), which gave a 500 and a message stuck in `pending`. Added AC-58 (T-12) |
| 0.4 | 2026-11-10 | Q7 (found while starting T-6, approved by the user): the Claude docs list `maxLength`/`minLength` and numeric limits as not supported in strict tool schemas, and `messages.create` sends schemas unchanged. FR-33: they are removed from `input_schema` only; GET /tools and executor validation keep them. AC-43 and AC-53 extended. A real-API check was prepared but not run (no API credits) |
| 0.5 | 2026-11-10 | Separation of concerns made explicit (approved by the user while starting T-6): new NFR-12 (S1:30) with AC-59 (import boundaries, T-6; the routes/`app.models` rule from T-8), AC-60 (neutral `LLMResult`, T-7) and AC-61 (tool names in the prompt from the registry, T-6). FR-24 wording extended. Architecture §2.1 and D8 added |
| 0.6 | 2026-11-10 | Scope review against S1 (approved by the user): removed what S1 doesn't ask for. FR-33: no `strict`, no `additionalProperties`, `input_schema` = `parameters` unchanged (Q7 and R9 no longer apply). FR-36: no `thinking` parameter, `LLM_EFFORT` setting removed, effort fixed at `medium`. AC-43 and AC-53 reworded. Requirements doc: REQ-51 (S1:30) added → NFR-12 |
| 0.7 | 2026-11-10 | LLM provider changed from Claude to Google Gemini (user's decision: Gemini credits). New D9 and FR-37 (internal format; only `app/llm` translates to Gemini). FR-10, FR-15, FR-25 (own `LLMUnavailableError`), FR-26, FR-33, FR-36, NFR-3, NFR-12, A3 reworded. AC-43, 47, 53, 58, 59, 60 reworded; AC-62, AC-63 added. Env var `ANTHROPIC_API_KEY` → `GEMINI_API_KEY`. New task T-7b. Risk R1 (found in a real-Gemini check: "What is 1/0?" answered without the calculator, 0/3): calculator description in §6 and the D0 app instructions now say that impossible or trivial math also goes to the calculator |

---

# Test plan

## 10. Levels and tools

- **Unit:** tools, executor, system-prompt builder. Plain pytest functions.
- **Integration:** API + services + SQLite (temporary files) + fake LLM, through FastAPI `TestClient`.
- **Manual / real LLM (stage 5):** a few curl checks with a real API key. Tests marked `@pytest.mark.real_llm` are skipped when no key is set.
- **Docker (stage 5):** manual checks of NFR-2 and NFR-3.

**Controls**
- The fake LLM (S3 §11) returns scripted blocks and stop reasons and records requests.
- Weather uses `random.Random(42)`.
- The clock is injected as `2026-11-10T12:00:00Z`. For ordering tests it's a ticking clock that adds 1 s per call.
- Seed date `2026-11-10` and seed 7.
- `TOOL_TIMEOUT_S = 1.0` in timeout tests. A "slow tool" is made by monkeypatching a real tool's `run` to wait on a `threading.Event`, which the test sets at teardown, so no thread is left running. No extra tool is registered, so there are always 5 tools.
- The app is built by `create_app(settings)`, so tests can build it with temporary files and build it a second time on the same files (restart test).
- `sample.db` and `app.db` go in the pytest `tmp_path`.
- `conftest.py` unsets `GEMINI_API_KEY` and blocks network sockets for every test.

**Commands**
- All tests: `pytest`
- One test: `pytest -k test_ac_12`
- In Docker: `docker compose run --rm api pytest`
- Real-LLM checks: `pytest -m real_llm` (needs a key)

**Exit criteria**
- Every automated AC passes.
- The 6 required tests (§12) pass.
- Every manual AC is passed or explicitly waived by the user.
- No open failures.

## 11. Acceptance criteria

Abbreviations: **auto** = automated, **man** = manual. "Fake returns X" means the fake LLM's scripted response.

### Conversations
| AC | FR/NFR | Given / When / Then | Level | Test |
|---|---|---|---|---|
| AC-1 | FR-1 | **When** `POST /conversations {}` **then** 201, `id` matches `^conv_[0-9a-f]{12}$`, `created_at` is ISO 8601; a 4,001-char system_prompt → 422 | int auto | `test_ac_1_create_conversation` |
| AC-2 | FR-1, FR-24 | **Given** no system_prompt, and separately system_prompt "   " **when** a message is sent **then** in both cases the fake received system = APP_INSTRUCTIONS + "\n\nYou are a helpful assistant.", and GET shows `system_prompt: null` | int auto | `test_ac_2_default_system_prompt` |
| AC-3 | FR-24 | **Given** system_prompt "Answer in French." **when** 2 turns are sent **then** both LLM requests have the identical system string ending in "Answer in French." | int auto | `test_ac_3_system_prompt_stable` |
| AC-4 | FR-2 | **Given** a ticking clock, and conversations A then B **when** `GET /conversations` **then** [B, A] with `message_count` 0 and `last_message_at` null | int auto | `test_ac_4_list_conversations` |
| AC-5 | FR-3 | **Given** a turn with one tool **when** `GET /conversations/{id}` **then** messages = [user, assistant], each with `created_at`, and the assistant has `status: complete`, `tools_used` (1 item) and `tokens_used` | int auto | `test_ac_5_get_history` |
| AC-6 | FR-4 | **Given** a conversation with a tool turn **when** DELETE **then** 204; GET → 404; 0 Message and 0 ToolExecution rows remain for it | int auto | `test_ac_6_delete_cascades` |
| AC-7 | FR-5 | **Given** system_prompt "X" and 2 turns **when** reset **then** 200 `{id, message_count: 0}`; GET shows `messages: []` and system_prompt "X"; 0 ToolExecution rows | int auto | `test_ac_7_reset` |
| AC-8 | FR-6 | **When** GET, DELETE, reset, send on `conv_000000000000` **then** each returns 404 | int auto | `test_ac_8_unknown_conversation_404` |
| AC-9 | FR-7 | **When** a turn completes **then** `last_message_at` ≥ the assistant message's `created_at` | int auto | `test_ac_9_last_message_at` |

### Chat and tool loop
| AC | FR/NFR | Given / When / Then | Level | Test |
|---|---|---|---|---|
| AC-10 | FR-8, FR-11, FR-10 | **Required test 1 (basic chat).** **Given** fake returns text "Hello!" with `end_turn` **when** "Hi" is sent **then** 200 `{message: {role: assistant, content: "Hello!"}, tools_used: [], tokens_used}`; exactly 1 LLM call, with 5 tools and `tool_choice: auto` | int auto | `test_ac_10_basic_chat_no_tools` |
| AC-11 | FR-9 | **When** content is "", "   " or 10,001 chars **then** 422 | int auto | `test_ac_11_content_validation` |
| AC-12 | FR-9 | **When** an invalid body is sent to an unknown id **then** 422 (not 404) | int auto | `test_ac_12_validation_before_404` |
| AC-13 | FR-12, FR-14 | **Required test 2 (single tool).** **Given** fake returns tool_use calculator `{"expression": "25/100*180"}`, then text "45" **when** "What's 25% of 180?" is sent **then** 200, content "45", `tools_used = [{tool: calculator, input: {...}, output: {result: 45.0}, success: true, error: null, execution_time_ms ≥ 0}]`; 2 LLM calls; the 2nd request ends with a user message holding 1 tool_result whose `tool_use_id` equals the tool_use block's `id` | int auto | `test_ac_13_single_tool` |
| AC-14 | FR-13 | **Required test 3 (multiple tools).** **Given** fake returns one response with tool_use weather `{"location": "Tokyo"}` (id "tu_1") and calculator `{"expression": "85*0.15"}` (id "tu_2"), then text **when** sent **then** both run; the 2nd LLM request has ONE user message with 2 tool_results with `tool_use_id` "tu_1", "tu_2" in that order; `tools_used` = [weather, calculator], both success; calculator output 12.75 | int auto | `test_ac_14_multiple_tools` |
| AC-15 | FR-13 | **Given** weather's `run` patched to wait 0.2 s, and one response requesting weather then calculator **then** `tools_used` and tool_results are [weather, calculator] (request order, although calculator finishes first) | int auto | `test_ac_15_result_order` |
| AC-16 | FR-16, FR-27 | **Required test 4 (tool error).** **Given** fake requests calculator `{"expression": "1/0"}`, then text **then** 200; `tools_used[0]` has success false, output null, error "Division by zero"; the 2nd LLM request's tool_result has `is_error: true` and content containing "Division by zero" | int auto | `test_ac_16_tool_error_handled` |
| AC-17 | FR-16, FR-17 | **Given** fake requests calculator `{"expr": "1"}` **then** an error result starting "Invalid input:"; request 200 | int auto | `test_ac_17_invalid_params` |
| AC-18 | FR-16 | **Given** fake requests tool `teleport` **then** error "Unknown tool: teleport"; request 200 | int auto | `test_ac_18_unknown_tool` |
| AC-19 | FR-18, FR-34, NFR-8 | **Given** `TOOL_TIMEOUT_S=1.0`, weather's `run` patched to block on an Event (released at teardown), and one response requesting weather and calculator `2+2` **then** the whole request takes < 1.5 s; weather has success false and error "Timed out after 1s"; calculator has result 4.0 (partial results); 2 ToolExecution rows, the weather one with success false | int auto | `test_ac_19_timeout_partial_results` |
| AC-20 | FR-15, FR-34 | **Given** fake returns tool_use calculator `1+1` 6 times, then text **then** 5 tool rounds run; the 6th response's call gets the error "Tool call limit reached" without running; the 7th LLM call has `tool_choice: none`; 200 with the final text; 7 LLM calls in total; `tools_used` has 6 items, the 6th with success false and `execution_time_ms` 0; 6 ToolExecution rows | int auto | `test_ac_20_round_limit` |
| AC-21 | FR-19 | **Given** fake usages (10 in, 5 out) then (20 in, 7 out) **then** `tokens_used` = 42 in the response and in history | int auto | `test_ac_21_token_sum` |
| AC-22 | FR-20 | **Given** a new conversation **when** the first message is sent **then** the LLM request `messages` = [that user message] only | int auto | `test_ac_22_first_message` |

### History and context
| AC | FR/NFR | Given / When / Then | Level | Test |
|---|---|---|---|---|
| AC-23 | FR-21, FR-3 | **Required test 5 (conversation history).** **Given** turn 1 used weather for Paris **when** turn 2 "And is that warm?" is sent **then** the turn 2 request has, in order: turn-1 user, turn-1 assistant with tool_use, user with tool_result, turn-1 final assistant text, then the turn-2 user message; GET history shows 4 messages in order | int auto | `test_ac_23_multi_turn_history` |
| AC-24 | FR-22 | **Given** fake round 1 returns [thinking(signature "sig1"), tool_use] **then** the round 2 request contains that thinking block unchanged; the stored `llm_blocks` still contains it; **and** the next turn's request contains no thinking blocks | int auto | `test_ac_24_thinking_blocks` |
| AC-25 | FR-23 | **Given** 25 complete turns stored **when** turn 26 is sent **then** the request has turns 6-25 plus the new message, and its first message has role user | int auto | `test_ac_25_history_trim` |
| AC-26 | FR-21, FR-25, FR-3 | **Given** turn 1 failed (502) **when** turn 2 is sent **then** the request contains only turn 2's user message; GET history still shows turn 1's assistant message with status `error` and content "LLM service unavailable" | int auto | `test_ac_26_failed_turn_skipped` |

### LLM outcomes
| AC | FR/NFR | Given / When / Then | Level | Test |
|---|---|---|---|---|
| AC-58 | FR-25 | **Given** the real `LLMClient` with no `GEMINI_API_KEY` set (no fake) **when** a message is sent **then** 502 `{"detail": "LLM service unavailable"}`, and the assistant message has status `error` (not stuck in `pending`) with content "LLM service unavailable" | int auto | `test_ac_58_no_api_key_502` |
| AC-27 | FR-25, FR-34 | **Given** fake round 1 requests calculator, and round 2 raises an SDK connection error **then** 502 `{"detail": "LLM service unavailable"}`; the assistant message has status `error` and content "LLM service unavailable"; 1 ToolExecution row is still saved | int auto | `test_ac_27_llm_failure_502` |
| AC-28 | FR-26 | **Given** fake stop_reason `refusal` **then** 200, content "I can't help with that request.", status complete | int auto | `test_ac_28_refusal` |
| AC-29 | FR-26 | **Given** fake text "Partial" with `max_tokens` **then** content "Partial [response cut off]" | int auto | `test_ac_29_max_tokens` |
| AC-30 | FR-26 | **Given** fake stop_reason `weird_value` **then** 502 `{"detail": "Unexpected LLM response"}`; status `error`, content "Unexpected LLM response" | int auto | `test_ac_30_unexpected_stop` |
| AC-57 | FR-21, FR-26 | **Given** turn 1 ended with `refusal` **when** turn 2 is sent **then** the request has: turn-1 user text, an assistant text message "I can't help with that request.", then the turn-2 user message | int auto | `test_ac_57_replay_refusal_turn` |

### Tools (unit)
| AC | FR/NFR | Given / When / Then | Level | Test |
|---|---|---|---|---|
| AC-31 | FR-27 | `"2 + 2"`→4.0; `"sqrt(16)"`→4.0; `"sin(3.14159/2)"`→1.0 (±1e-5); `"100 * (1 + 0.05)^10"`→162.889 (±0.001); `"sqrt(144) + 5"`→17.0 | unit auto | `test_ac_31_calculator_examples` |
| AC-32 | FR-27 | `"1/0"`→"Division by zero"; `"2 +"`, `"sqrt(-1)"`, `"log(0)"`, `"sqrt(1, 2)"`→"Invalid expression"; `"9**9**9"`→"Exponent too large"; `"10.0**400"`, `"1e999"`, `"1e308*10"`, `"((2**1000)**1000)**1000"`→"Result too large"; every result is JSON-serialisable (no inf/nan) | unit auto | `test_ac_32_calculator_errors` |
| AC-33 | NFR-5 | `"__import__('os')"`, `"().__class__"`, `"open('x')"`, `"a+1"` → "Invalid expression"; a 201-char expression → "Invalid input:" (through the executor); the module source contains no `eval(` or `exec(` | unit auto | `test_ac_33_calculator_security` |
| AC-34 | FR-28 | `"python"`→ ≥1 result, each with title/snippet/url; `"zzqx"`→`[]` | unit auto | `test_ac_34_web_search` |
| AC-35 | FR-29 | With `Random(42)`: same output on two calls with fresh generators; temperature, condition and humidity within FR-29 ranges over 100 calls | unit auto | `test_ac_35_weather` |
| AC-36 | FR-30, NFR-10 | Seed date 2026-11-10, seed 7: `SELECT COUNT(*) FROM orders WHERE order_date >= '2026-10-01' AND order_date < '2026-11-01'` (literal dates, never `date('now')` in tests) returns one row with the exact golden count. The count is computed once when the seeder is written and fixed in the test, so the test fails if the seed data changes. Seeding twice gives identical data, and all `order_date` are within 2025-11-10..2026-11-10 | unit auto | `test_ac_36_database_query` |
| AC-37 | FR-30 | `SELECT * FROM orders` → 100 rows, `row_count` 100, `truncated: true` | unit auto | `test_ac_37_database_row_limit` |
| AC-38 | NFR-6 | INSERT, UPDATE, DELETE, DROP TABLE, CREATE TABLE, ATTACH, PRAGMA, `SELECT 1; SELECT 2`, and `SELECT * FROM conversations` → all error results; row counts unchanged | unit auto | `test_ac_38_database_security` |
| AC-39 | NFR-6 | `WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c` (it must finish before returning any row) is aborted with an error result within 3 s | unit auto | `test_ac_39_database_query_timeout` |
| AC-40 | FR-31 | Clock 2026-11-10T12:00:00Z: `current` tz Asia/Tokyo → `2026-11-10T21:00:00+09:00`; `convert` 2026-11-10T12:00:00 Europe/London→Asia/Tokyo → `2026-11-10T21:00:00+09:00`; `calculate` 2026-11-10T12:00:00 +30 days → `2026-12-10T12:00:00`; days −10 → `2026-10-31T12:00:00` | unit auto | `test_ac_40_datetime_operations` |
| AC-41 | FR-31, FR-17 | Timezone "Mars/Base" → "Unknown timezone: Mars/Base"; `convert` without `to_tz` → "Invalid input:"; `calculate` without days/hours/minutes → "Invalid input:"; `convert` with datetime `2026-11-10T12:00:00+02:00` → "Invalid input: datetime must not include an offset for convert"; every success output has exactly the key `result` | unit auto | `test_ac_41_datetime_errors` |
| AC-42 | FR-32 | `GET /tools` → 5 tools, each with name, description, and `parameters.type == "object"` | int auto | `test_ac_42_list_tools` |
| AC-43 | FR-33, FR-36 | The Gemini request (recording stub) has 5 function declarations, each exactly `{name, description, parameters_json_schema}` with the schema equal to the tool's `parameters` from `GET /tools`; **given** `LLM_MODEL=test-model` the request has model "test-model", `max_output_tokens` 16000, the system prompt as `system_instruction`, mode `AUTO` and no thinking settings; with `LLM_MODEL` unset, model "gemini-3.1-flash-lite" | int auto | `test_ac_43_llm_request_settings` |

### Logging, health, platform
| AC | FR/NFR | Given / When / Then | Level | Test |
|---|---|---|---|---|
| AC-44 | FR-34 | **Required test 6 (logging).** **Given** a turn with calculator `2+2` (ok) and `1/0` (error) **then** 2 ToolExecution rows linked to the assistant message id: the first has success true, output {result: 4.0}, error_message null; the second has success false, error_message "Division by zero"; both have execution_time_ms ≥ 0 | int auto | `test_ac_44_tool_execution_logging` |
| AC-45 | FR-35 | `GET /health` → 200 `{"status": "ok"}` | int auto | `test_ac_45_health` |
| AC-46 | NFR-4 | **Given** a conversation created through `create_app(settings)` **when** a second `create_app(settings)` is built on the same files **then** GET on the second app returns it with its messages | int auto | `test_ac_46_persistence_restart` |
| AC-47 | NFR-9, NFR-3 | Inside the test suite: `GEMINI_API_KEY` is not set, `socket.create_connection(("example.com", 80))` raises an error, and the app starts and serves `/health` (the LLM client is created lazily) | int auto | `test_ac_47_no_network_no_key` |
| AC-48 | NFR-2 | `docker compose up --build` → `/health` 200 within 60 s; create a conversation and send "What's 2+2?" with a real key → 200 | man | stage 5 |
| AC-49 | NFR-3 | `docker compose run --rm api pytest` passes without a key | man | stage 5 |
| AC-50 | NFR-1 | The Dockerfile base image is `python:3.12-slim`; `python --version` in the container shows 3.12 | man | stage 5 |
| AC-51 | NFR-7 | `git check-ignore .env` matches; `.env.example` lists every variable with empty values; no `sk-ant` string in the repo (`git grep`) | man | stage 6 |
| AC-52 | NFR-11 | The README has the 6 S1 sections + D1-D5 + the SQL deviation; AI_USAGE.md follows the template; the S1:376-385 files exist | man | stage 6 |

### Architecture (separation of concerns)

| AC | Requirement | Criterion | Level | Test |
|---|---|---|---|---|
| AC-59 | NFR-12 | Parsing every `app/**/*.py` with `ast` finds no forbidden import: `app/tools` imports only the standard library, `jsonschema` and `app.tools.*`; `app/services` imports no `fastapi`/`google.genai`; only `app/llm` imports `google.genai`, and `app/llm` doesn't import `app.config`; `app/api` imports no `sqlalchemy` except `sqlalchemy.orm.Session`, and (from T-8) no `app.models` | unit auto | `test_ac_59_layer_imports` |
| AC-60 | NFR-12 | `LLMClient.complete` turns a Gemini SDK response (recording stub) into an `LLMResult` (text, tool calls, stop reason, tokens, blocks) with no SDK types inside; the fake LLM returns `LLMResult` too | unit auto | `test_ac_60_llm_result` |
| AC-61 | NFR-12, FR-24 | **Given** an app built with a registry holding only calculator **when** a message is sent **then** the system prompt names calculator and none of the other tools; with the full registry it names every registered tool in registry order | int auto | `test_ac_61_prompt_tools_from_registry` |
| AC-62 | FR-37, FR-13 | **Given** internal messages [user text, assistant [thinking with signature "sig1", text, tool_use weather id "c1", tool_use calculator id "c2"], user [tool_result c1 ok, tool_result c2 is_error "Division by zero"]] **when** the LLM layer builds the Gemini request **then** contents are [user, model, user]; the model Content holds a thought part with signature "sig1", a text part and 2 `function_call` parts (ids c1, c2); the last user Content holds exactly 2 `function_response` parts in order, with ids c1/c2, names weather/calculator, `{"result": ...}` for c1 and `{"error": "Division by zero"}` for c2 | unit auto | `test_ac_62_gemini_request_translation` |
| AC-63 | FR-37, FR-26 | **Given** recorded Gemini responses **then** the `LLMResult` has: function_call parts → stop `tool_use` with tool calls (id, name, args) in order and the part's `thought_signature` kept on the block; `STOP` → `end_turn`; `MAX_TOKENS` → `max_tokens`; `SAFETY` and a blocked prompt → `refusal`; `OTHER` → "OTHER"; tokens 12 in and 5 + 3 out from `prompt_token_count` 12, `candidates_token_count` 5, `thoughts_token_count` 3 | unit auto | `test_ac_63_gemini_response_mapping` |

### Real-LLM checks (stage 5, risk R1/R5)
| AC | FR | Given / When / Then | Level |
|---|---|---|---|
| AC-53 | FR-10, FR-12, FR-33 | Real LLM, "What's 15% tip on $85?" → the request with all 5 function declarations is accepted (no 400), calculator is used, and the answer contains 12.75 | man / real_llm |
| AC-54 | FR-13 | Real LLM, "What's the weather and time in London?" → weather and datetime are both used | man / real_llm |
| AC-55 | FR-21, FR-22 | Real LLM, 3 turns with tools, then "What did you calculate earlier?" → no API error (history replay is accepted) and the answer refers to the earlier result | man / real_llm |
| AC-56 | FR-30 | Real LLM, "How many orders were placed last month?" → database_query is used, and the answer gives a number | man / real_llm |

## 12. The 6 required tests (S1:348-354)

| S1 required test | AC | Test |
|---|---|---|
| Basic chat without tools | AC-10 | `test_ac_10_basic_chat_no_tools` |
| Single tool usage | AC-13 | `test_ac_13_single_tool` |
| Multiple tool usage | AC-14 | `test_ac_14_multiple_tools` |
| Tool error handling | AC-16 | `test_ac_16_tool_error_handled` |
| Conversation history | AC-23 | `test_ac_23_multi_turn_history` |
| Tool execution logging | AC-44 | `test_ac_44_tool_execution_logging` |

## 13. Traceability

| Requirement | AC |
|---|---|
| FR-1 | 1, 2 |
| FR-2 | 4 |
| FR-3 | 5, 23, 26 |
| FR-4 | 6 |
| FR-5 | 7 |
| FR-6 | 8 |
| FR-7 | 9 |
| FR-8 | 10 |
| FR-9 | 11, 12 |
| FR-10 | 10, 53 |
| FR-11 | 10 |
| FR-12 | 13, 53 |
| FR-13 | 14, 15, 54 |
| FR-14 | 13, 16 |
| FR-15 | 20 |
| FR-16 | 16, 17, 18 |
| FR-17 | 17, 41 |
| FR-18 | 19 |
| FR-19 | 21 |
| FR-20 | 22 |
| FR-21 | 23, 26, 55, 57 |
| FR-22 | 24, 55 |
| FR-23 | 25 |
| FR-24 | 2, 3, 61 |
| FR-25 | 26, 27, 58 |
| FR-26 | 28, 29, 30, 57 |
| FR-27 | 16, 31, 32 |
| FR-28 | 34 |
| FR-29 | 35 |
| FR-30 | 36, 37, 56 |
| FR-31 | 40, 41 |
| FR-32 | 42 |
| FR-33 | 43 |
| FR-34 | 19, 20, 27, 44 |
| FR-35 | 45 |
| FR-36 | 43 |
| FR-37 | 62, 63 |
| NFR-1 | 50 |
| NFR-2 | 48 |
| NFR-3 | 47, 49 |
| NFR-4 | 46 |
| NFR-5 | 33 |
| NFR-6 | 38, 39 |
| NFR-7 | 51 |
| NFR-8 | 19 |
| NFR-9 | 47 |
| NFR-10 | 36 |
| NFR-11 | 52 |
| NFR-12 | 59, 60, 61 |

**Coverage the other way:** every AC (1-61) cites at least one FR/NFR. Every in-scope S2 requirement maps to an FR/NFR:
- REQ-1..38, 40-42 and 51 (→ NFR-12) are covered.
- REQ-47..50 are covered by NFR-11.
- REQ-39 and 43..46 are out of scope (§2).

## 14. Review checklist (run 2026-11-10)

| Check | Result |
|---|---|
| Every S1/S2 item is in the spec, out of scope, or open questions | Pass. REQ-1..50 mapped (§13). The 7 edge cases → AC-10, 16, 14, 17, 19, 20, 22 |
| No placeholder text or `[NEEDS CLARIFICATION]` | Pass |
| No vague words; numbers have units | Pass (s, chars, rows, °C) |
| IDs unique and consistently referenced | Pass (FR-1..36, NFR-1..12, AC-1..61) |
| Each FR has an AC; each AC is testable without reading the code | Pass |
| Independent review v0.1 (17 findings) | All applied in v0.2 (see change log) |
