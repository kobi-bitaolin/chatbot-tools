# Verification report: chatbot-tools

- **Stage:** 5, test execution
- **Spec:** `docs/chatbot-spec.md` v0.10 (Approved)
- **Source:** `chatbot-tool.md` (S1)
- **Run on:** 2026-11-10, `main` at `1da95cf`, model `gemini-3.1-flash-lite` (default)
- **Result:** every acceptance criterion that belongs to stage 5 passes. AC-51 and AC-52 belong to stage 6.

## 1. Automated test runs (S1:348, NFR-3)

| Where | Command | Key | Result |
|---|---|---|---|
| Local (Python 3.12.4) | `pytest -q` | not used (tests remove it) | **127 passed**, 4 deselected (real-LLM), 10.8 s |
| Docker, plain image | `docker run --rm chatbot-tools-api pytest -q` | none in the container | **127 passed**, 4 deselected, 14.2 s |
| Docker, compose (AC-49) | `docker compose run --rm api pytest -q` | `.env` loaded, removed by the test fixtures | **127 passed**, 4 deselected, 14.3 s |
| Local, real Gemini | `pytest -m real_llm -v` | `.env` | **4 passed** (AC-53..56), 16.8 s |
| Local, everything | `pytest -q -m "real_llm or not real_llm"` | `.env` | **131 passed**, 25.7 s |

The 131 tests are 106 named after an AC (`test_ac_N_...`, some parametrised) and 25 named after an FR/NFR (`test_fr_N_...`, `test_nfr_N_...`, executor tests).

### The 6 required tests (S1:348-354)

All exist, pass, and assert real behavior. Each one was also mutation-checked in stage 4: deliberately breaking the code made it fail.

| S1 test | AC | Test | Asserts |
|---|---|---|---|
| Basic chat without tools | AC-10 | `tests/test_api_chat.py::test_ac_10_basic_chat_no_tools` | 5 |
| Single tool usage | AC-13 | `tests/test_api_tool_loop.py::test_ac_13_single_tool` | 14 |
| Multiple tool usage | AC-14 | `tests/test_api_tool_loop.py::test_ac_14_multiple_tools` | 6 |
| Tool error handling | AC-16 | `tests/test_api_tool_loop.py::test_ac_16_tool_error_handled` | 6 |
| Conversation history | AC-23 | `tests/test_api_history.py::test_ac_23_multi_turn_history` | 12 |
| Tool execution logging | AC-44 | `tests/test_api_tool_loop.py::test_ac_44_tool_execution_logging` | 13 |

## 2. Real system (Docker + real Gemini)

`docker compose up -d --force-recreate` with `API_PORT=8001` and `GEMINI_API_KEY` in `.env`.

- `/health` returned 200 **2 s** after start (AC-48 allows 60 s); the container reports `healthy`.
- Image `python:3.12-slim`, `python --version` → **3.12.16**, runs as the non-root user `app` (AC-50).
- 15 real chat turns: **all HTTP 200**, 1.1-2.6 s each. Every error request got the expected 4xx.

### Saved curl examples

Each example sends `POST /conversations/{id}/messages` to `http://localhost:8001` with a JSON body. These are the README's examples.

```bash
curl -s -X POST localhost:8001/conversations -H 'Content-Type: application/json' -d '{}'
# 201 {"id":"conv_e190b1750285","created_at":"2026-11-10T19:44:55.194137Z"}
```

**No tools:** "Hello"
```json
{"message":{"role":"assistant","content":"Hello! How can I help you today?"},"tools_used":[],"tokens_used":761}
```

**One tool:** "What's 25% of 180?"
```json
{"message":{"role":"assistant","content":"25% of 180 is 45."},
 "tools_used":[{"tool":"calculator","input":{"expression":"0.25 * 180"},"output":{"result":45.0},"success":true,"error":null,"execution_time_ms":2}],
 "tokens_used":1716}
```

**Several tools in one round:** "What's the weather and time in London?"
```json
{"message":{"role":"assistant","content":"In London, it is currently 7:45 PM (19:45) and the weather is rainy with a temperature of 10°C."},
 "tools_used":[
  {"tool":"weather","input":{"location":"London"},"output":{"location":"London","temperature":10,"condition":"rainy","humidity":70},"success":true,"error":null,"execution_time_ms":2},
  {"tool":"datetime","input":{"operation":"current","timezone":"Europe/London"},"output":{"result":"2026-11-10T19:45:01.773859+00:00"},"success":true,"error":null,"execution_time_ms":7}],
 "tokens_used":1946}
```

**S1's own example:** "What's the weather in Tokyo and what's 15% tip on $85?"
```json
{"message":{"role":"assistant","content":"The current weather in Tokyo is sunny with a temperature of 12°C. A 15% tip on $85 is $12.75."},
 "tools_used":[
  {"tool":"weather","input":{"location":"Tokyo"},"output":{"location":"Tokyo","temperature":12,"condition":"sunny","humidity":43},"success":true,"error":null,"execution_time_ms":2},
  {"tool":"calculator","input":{"expression":"85 * 0.15"},"output":{"result":12.75},"success":true,"error":null,"execution_time_ms":2}],
 "tokens_used":1693}
```

**Tool error:** "What is 1/0?"
```json
{"message":{"role":"assistant","content":"I cannot calculate that because it is a division by zero, which is mathematically undefined."},
 "tools_used":[{"tool":"calculator","input":{"expression":"1/0"},"output":null,"success":false,"error":"Division by zero","execution_time_ms":1}],
 "tokens_used":2135}
```

**Follow-up that needs history**, in the same conversation as the turns above: "And what about Paris? Same question as London." The LLM called weather for Paris and datetime for `Europe/Paris`. Then "What did you calculate earlier?":
```json
{"message":{"role":"assistant","content":"Earlier, I performed the following calculations for you:\n\n1.  **2 + 2**: The result was 4.\n2.  **25% of 180**: The result was 45.\n3.  **1 / 0**: This resulted in an error because division by zero is mathematically undefined."},"tools_used":[],"tokens_used":1317}
```

**Database:** "How many orders were placed last month?"
```json
{"message":{"role":"assistant","content":"There were 40 orders placed last month."},
 "tools_used":[{"tool":"database_query","input":{"sql":"SELECT count(*) FROM orders WHERE order_date >= date('now', 'start of month', '-1 month') AND order_date < date('now', 'start of month')"},"output":{"columns":["count(*)"],"rows":[[40]],"row_count":1,"truncated":false},"success":true,"error":null,"execution_time_ms":9}],
 "tokens_used":1939}
```

**Database write blocked by the tool itself:** "Use the database_query tool to run exactly this SQL and tell me the result: DELETE FROM orders"
```json
{"message":{"role":"assistant","content":"The database tool is configured for read-only access and only permits `SELECT` statements. Therefore, I cannot execute the `DELETE` command you provided."},
 "tools_used":[{"tool":"database_query","input":{"sql":"DELETE FROM orders"},"output":null,"success":false,"error":"Query rejected: only one read-only SELECT is allowed","execution_time_ms":3}],
 "tokens_used":1633}
```
A later `SELECT COUNT(*) FROM orders` still returned 500.

**Unknown timezone:** "What time is it in Atlantis/Nowhere?" → 200, datetime error "Unknown timezone: Atlantis/Nowhere", and the answer asks for a valid timezone.

**Custom system prompt:** `{"system_prompt": "Answer in French."}`, then "What's 10 times 7?" → "10 fois 7 est égal à 70." (calculator used).

**Errors and conversation management:**

| Request | Response |
|---|---|
| send `{"content": ""}` | 422 `string_too_short` |
| send to `conv_000000000000` | 404 `{"detail":"Conversation not found"}` |
| send `{"content": ""}` to `conv_000000000000` | 422 (validation before 404, FR-9) |
| `GET /conversations/{id}` | 200, every message in order, each assistant message with `status`, `tools_used`, `tokens_used` |
| `GET /conversations` | 200, newest first, with `message_count` and `last_message_at` |
| `POST /conversations/{id}/reset` | 200 `{"id":..., "message_count":0}`; GET then shows `messages: []` and keeps the system prompt |
| `DELETE /conversations/{id}` | 204; GET then 404 |

### Tool execution logging (S1:300-310, FR-34)

`tool_executions` in `/app/data/app.db` (read-only connection, inside the container) has the columns `id, message_id, tool_name, input, output, success, error_message, execution_time_ms, created_at`. All 62 rows from the runs are there. Successes and failures are both logged, for example:

| tool | input | output | success | error_message | ms |
|---|---|---|---|---|---|
| database_query | `{"sql": "DELETE FROM orders"}` | null | 0 | Query rejected: only one read-only SELECT is allowed | 3 |
| datetime | `{"timezone": "Atlantis/Nowhere", "operation": "current"}` | null | 0 | Unknown timezone: Atlantis/Nowhere | 8 |
| calculator | `{"expression": "85 * 0.15"}` | `{"result": 12.75}` | 1 | null | 2 |

### Manual checks by the user (2026-11-10)

The user ran 10 checks in Swagger (`/docs`) on the same container: health, create/list, calculator, two tools in one turn, database count, read-only refusal, follow-up from history, unknown-timezone error, 422/404, history + reset + delete. **All 10 passed.** The optional no-key check (AC-58 by hand) was explained, but its result was not reported. AC-58 passes as an automated test.

## 3. Edge cases (S1:325-333)

| # | S1 edge case | Evidence | Result |
|---|---|---|---|
| 1 | No tools needed → respond directly | AC-10; real "Hello" → `tools_used: []` | pass |
| 2 | Tool returns error → inform the user | AC-16, AC-41; real "1/0" and "Atlantis/Nowhere" → 200 with a clear answer | pass |
| 3 | Multiple tools → execute all, combine | AC-14, AC-15, AC-54; real London and Tokyo questions, both tools in one round | pass |
| 4 | Invalid tool parameters → validation errors | AC-17, AC-18, AC-33 (fake LLM sends bad arguments: "Invalid input: ...", "Unknown tool: ...") | pass (automated only: real Gemini always sent valid arguments) |
| 5 | Tool timeout → partial results or error | AC-19 (blocked weather → "Timed out after 1s", calculator result still returned, < 1.5 s), AC-39 (slow SQL aborted < 3 s) | pass (automated only: real tools finish in ms) |
| 6 | Recursive tool calls → no infinite loops | AC-20 (5 rounds, then "Tool call limit reached" and a last call with tools off) | pass (automated only) |
| 7 | Empty conversation → first message | AC-22; every real conversation above started with an empty history | pass |

## 4. Acceptance criteria

`pass` = automated test passed in all runs of §1. `manual-pass` = checked by hand in §2.

| AC | What | Result | Evidence |
|---|---|---|---|
| AC-1 | create conversation, id format, prompt length | pass | `test_ac_1_create_conversation` |
| AC-2 | default system prompt | pass | `test_ac_2_default_system_prompt` |
| AC-3 | system prompt stable across turns | pass | `test_ac_3_system_prompt_stable` |
| AC-4 | list conversations, newest first | pass | `test_ac_4_list_conversations` |
| AC-5 | get history | pass | `test_ac_5_get_history` |
| AC-6 | delete cascades | pass | `test_ac_6_delete_cascades` |
| AC-7 | reset | pass | `test_ac_7_reset` |
| AC-8 | unknown conversation → 404 | pass | `test_ac_8_unknown_conversation_404` |
| AC-9 | `last_message_at` | pass | `test_ac_9_last_message_at` |
| AC-10 | **required 1:** basic chat | pass | `test_ac_10_basic_chat_no_tools` |
| AC-11 | content validation | pass | `test_ac_11_content_validation` |
| AC-12 | 422 before 404 | pass | `test_ac_12_validation_before_404` |
| AC-13 | **required 2:** single tool | pass | `test_ac_13_single_tool` |
| AC-14 | **required 3:** multiple tools | pass | `test_ac_14_multiple_tools` |
| AC-15 | results keep request order | pass | `test_ac_15_result_order` |
| AC-16 | **required 4:** tool error | pass | `test_ac_16_tool_error_handled` |
| AC-17 | invalid parameters, unexpected fields | pass | `test_ac_17_invalid_params` (2 cases) |
| AC-18 | unknown tool | pass | `test_ac_18_unknown_tool` |
| AC-19 | timeout, partial results | pass | `test_ac_19_timeout_partial_results` |
| AC-20 | round limit | pass | `test_ac_20_round_limit` |
| AC-21 | token sum | pass | `test_ac_21_token_sum` |
| AC-22 | first message | pass | `test_ac_22_first_message` |
| AC-23 | **required 5:** history | pass | `test_ac_23_multi_turn_history` |
| AC-24 | thinking blocks replay | pass | `test_ac_24_thinking_blocks` |
| AC-25 | history trim to 20 turns | pass | `test_ac_25_history_trim` |
| AC-26 | failed turn skipped in replay | pass | `test_ac_26_failed_turn_skipped` |
| AC-27 | LLM failure → 502 | pass | `test_ac_27_llm_failure_502` |
| AC-28 | refusal | pass | `test_ac_28_refusal` |
| AC-29 | `max_tokens` cut-off | pass | `test_ac_29_max_tokens` |
| AC-30 | unexpected stop reason → 502 | pass | `test_ac_30_unexpected_stop` |
| AC-31 | calculator examples | pass | `test_ac_31_calculator_examples` |
| AC-32 | calculator errors | pass | `test_ac_32_calculator_errors` (12 cases) |
| AC-33 | calculator security | pass | `test_ac_33_calculator_security` (8 cases) |
| AC-34 | web search mock | pass | `test_ac_34_web_search` |
| AC-35 | weather mock, °C | pass | `test_ac_35_weather` |
| AC-36 | database golden count | pass | `test_ac_36_database_query` |
| AC-37 | 100-row limit | pass | `test_ac_37_database_row_limit` |
| AC-38 | database security | pass | `test_ac_38_database_security` (10 cases); also the real forced `DELETE` in §2 |
| AC-39 | slow query aborted | pass | `test_ac_39_database_query_timeout` |
| AC-40 | datetime operations | pass | `test_ac_40_datetime_operations` |
| AC-41 | datetime errors | pass | `test_ac_41_datetime_errors` (8 cases) |
| AC-42 | `GET /tools` | pass | `test_ac_42_list_tools` |
| AC-43 | Gemini request settings | pass | `test_ac_43_llm_request_settings` |
| AC-44 | **required 6:** logging | pass | `test_ac_44_tool_execution_logging`; also the real rows in §2 |
| AC-45 | health | pass | `test_ac_45_health` |
| AC-46 | data survives a restart | pass | `test_ac_46_persistence_restart` |
| AC-47 | no network, no key | pass | `test_ac_47_no_network_no_key` |
| AC-48 | `docker compose up`, real "What's 2+2?" | manual-pass | §2: health 200 after 2 s; "What's 2+2?" → 200, "2 + 2 is 4.", calculator used |
| AC-49 | suite in Docker without a key | manual-pass | §1: 127 passed in both Docker runs |
| AC-50 | Python 3.12 image | manual-pass | §2: `python:3.12-slim`, 3.12.16 |
| AC-51 | secrets not in the repo | stage 6 | planned in the spec |
| AC-52 | README and AI_USAGE.md | stage 6 | planned in the spec |
| AC-53 | real: tip on $85 | pass | `test_ac_53_real_calculator` |
| AC-54 | real: weather and time in London | pass | `test_ac_54_real_two_tools`; also §2 |
| AC-55 | real: history replay | pass | `test_ac_55_real_history_replay`; also §2 "What did you calculate earlier?" |
| AC-56 | real: orders last month | pass | `test_ac_56_real_database`; also §2 (40) |
| AC-57 | refusal turn replay | pass | `test_ac_57_replay_refusal_turn` |
| AC-58 | no API key → 502 | pass | `test_ac_58_no_api_key_502` |
| AC-59 | layer import rules | pass | `test_ac_59_layer_imports` (2 cases) |
| AC-60 | neutral `LLMResult` | pass | `test_ac_60_llm_result` (3 cases) |
| AC-61 | prompt tool names from the registry | pass | `test_ac_61_prompt_tools_from_registry` (2 cases) |
| AC-62 | Gemini request translation | pass | `test_ac_62_gemini_request_translation` |
| AC-63 | Gemini response mapping | pass | `test_ac_63_gemini_response_mapping` (10 cases) |

**Totals:** 63 AC; 58 pass, 3 manual-pass, 2 belong to stage 6, 0 fail.

## 5. Known limitations

1. **Weather is a random mock** (S1:197). The values are believable on their own, but they ignore city and season ("Paris 41°C" in November), and the same question gives different values each time.
2. **Web search is a mock** with fixed results for a few common queries; anything else returns `[]`.
3. **Real-LLM answers vary.** Gemini's wording, and sometimes which tools it calls, differ between runs. The real-LLM tests check behavior (which tools, key numbers), not exact text.
4. **Some edge cases are proven only with the fake LLM:** invalid parameters, timeouts and the round limit. Real Gemini sends valid arguments, and the real tools finish in milliseconds.
5. **Long conversations are trimmed, not summarized.** Only the last 20 turns are sent to the LLM (FR-23); older turns stay in the history but the LLM no longer sees them.
6. **Not built** (Should/Nice items deferred, see `docs/STATUS.md`): streaming, custom tool registration, tool usage analytics, conversation summarization, rate limiting, a real weather API.
7. **"Last month" depends on the date.** The seeded orders cover the year before the seed date, so the count for "last month" changes with the calendar. AC-36 uses fixed dates for this reason.
