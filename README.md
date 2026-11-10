# chatbot-tools

A chat API where an LLM (Google Gemini) decides when to call tools: a calculator, web search, weather, a SQL database and date/time. The tool loop is hand-written, with no agent framework, so every step can be seen and tested: the LLM asks for tools, the app runs them, the results go back, and the LLM writes the answer.

**Stack:** Python 3.12, FastAPI, the `google-genai` SDK (default model `gemini-3.1-flash-lite`), SQLite with SQLAlchemy, pytest, Docker.

## 1. How to run the project

### With Docker (recommended)

```bash
cp .env.example .env          # then put your key in GEMINI_API_KEY
docker compose up --build
```

The API is on `http://localhost:8000`. Interactive docs, where you can try every endpoint, are at `http://localhost:8000/docs`. If port 8000 is taken, set `API_PORT=8001` in `.env`.

Data (`app.db` for conversations, `sample.db` for the database tool) lives in the Docker volume `chatbot-data`, so it survives restarts. `docker compose down -v` deletes it; on the next start the app creates empty tables and new sample data, made from a fixed seed and dated from that day.

### Without Docker

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory --port 8000
```

### Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | none | Needed to chat. The app starts without it; a message then gets 502 "LLM service unavailable" |
| `LLM_MODEL` | `gemini-3.1-flash-lite` | Which Gemini model to call |
| `TOOL_TIMEOUT_S` | `5` | Seconds the tools of one round may take together |
| `DATA_DIR` | `data` | Folder for `app.db` and `sample.db` |
| `API_PORT` | `8000` | Host port in Docker |

Empty values use the default. The key is never in the repo: `.env` is git-ignored.

## 2. How to run tests

```bash
pytest                                   # 127 tests, fake LLM, no key or network needed
docker compose run --rm api pytest       # the same suite inside the container
pytest -m real_llm                       # 4 extra tests against real Gemini (needs GEMINI_API_KEY)
```

The normal suite never calls the real LLM. It uses a **fake LLM** (`tests/fake_llm.py`) that returns scripted answers, so the tests are repeatable, free and offline: a test fixture even blocks internet access. Clocks and random generators are injected, so date and weather results are fixed in tests.

Tests are named after the acceptance criterion they prove, for example `test_ac_14_multiple_tools` proves AC-14 in `docs/chatbot-spec.md`. The 6 tests the assignment asks for:

| Required test | Test |
|---|---|
| Basic chat without tools | `tests/test_api_chat.py::test_ac_10_basic_chat_no_tools` |
| Single tool usage | `tests/test_api_tool_loop.py::test_ac_13_single_tool` |
| Multiple tool usage | `tests/test_api_tool_loop.py::test_ac_14_multiple_tools` |
| Tool error handling | `tests/test_api_tool_loop.py::test_ac_16_tool_error_handled` |
| Conversation history | `tests/test_api_history.py::test_ac_23_multi_turn_history` |
| Tool execution logging | `tests/test_api_tool_loop.py::test_ac_44_tool_execution_logging` |

Full results, with every acceptance criterion: `docs/chatbot-verification.md`.

## 3. Available tools

`GET /tools` lists them with their JSON Schema parameters.

| Tool | Input | Output | What it does |
|---|---|---|---|
| `calculator` | `expression` (max 200 chars) | `{"result": 45.0}` | Math with `+ - * / % ** ^`, parentheses, `sqrt sin cos tan log log10 exp abs round`, `pi`, `e`. A safe parser, never `eval` (see Security) |
| `web_search` | `query` (max 300 chars) | `{"results": [{title, snippet, url}]}` | **Mock:** fixed results for common words (python, fastapi, docker, sqlite, claude, tokyo); anything else gives `[]` |
| `weather` | `location` (max 100 chars) | `{location, temperature, condition, humidity}` | **Mock:** random but believable values; temperature in °C, snow only when it's cold |
| `datetime` | `operation`: `current`, `convert` or `calculate`, plus `timezone`, `datetime`, `from_tz`, `to_tz`, `days`, `hours`, `minutes` | `{"result": "2026-11-10T21:00:00+09:00"}` | Current time in a timezone, conversion between timezones, adding or subtracting days, hours and minutes |
| `database_query` | `sql` (one `SELECT`) | `{columns, rows, row_count, truncated}` | Read-only queries on a sample store: `users` (50), `products` (30), `orders` (500 over the last 12 months), `order_items`. At most 100 rows |

**A deliberate change from the assignment:** the brief says the database tool takes a natural-language question. Here the LLM translates the question into SQL, and the tool runs that SQL read-only. The tool description lists the tables and columns, and relative dates like "last month" use SQLite's `date('now', ...)`. This keeps the tool small and testable (SQL in, rows out), and the LLM is already good at writing SQL.

## 4. How multiple tool calls are handled

One user message is one **turn**, and a turn can have several LLM **rounds** (`app/services/chat.py`):

1. The LLM gets the history, the new message and the 5 tool definitions.
2. If it asks for tools, the executor (`app/tools/executor.py`) **runs all of them in parallel** on a thread pool, under one deadline for the whole round (`TOOL_TIMEOUT_S`).
3. The results go back to the LLM **in one message, in the order the LLM asked for them** (not the order they finished), each paired with its call by id. The LLM combines them into one answer.
4. If the answer needs a chain, for example a database query and then a calculation, that's another round.
5. **No infinite loops:** after 5 tool rounds, any further call gets the error "Tool call limit reached", and one last LLM call is made with tools switched off, so it has to answer in text.

Every tool call is saved as a `ToolExecution` row (tool, input, output, success, error message, time in ms), linked to the assistant message, and returned to the client in `tools_used`.

## 5. How tool errors are handled

A tool error never crashes the request. The executor turns every problem into a failed result:

| Problem | Error text the LLM and client see |
|---|---|
| The tool fails (e.g. `1/0`) | `Division by zero` |
| The LLM asks for a tool that doesn't exist | `Unknown tool: teleport` |
| Missing or wrong parameters (checked with JSON Schema) | `Invalid input: ...` |
| A parameter the tool doesn't have | `Invalid input: unexpected field 'precision'` |
| The tool is too slow | `Timed out after 5s`; the other tools of the round keep their results |
| A bug inside a tool | `Tool failed unexpectedly`; the traceback goes to the server log only |

The failed result goes back to the LLM marked as an error, so it explains the problem to the user in plain words. The client gets HTTP 200 with `success: false` and `error` in `tools_used`, and the failure is logged like any other call.

Errors of the LLM itself are different: they end the turn.

| LLM outcome | Response |
|---|---|
| No key, network error, provider error | 502 `{"detail": "LLM service unavailable"}` |
| A stop reason the app doesn't know | 502 `{"detail": "Unexpected LLM response"}` |
| Refusal | 200, "I can't help with that request." |
| Answer cut off by the token limit | 200, the text so far + " [response cut off]" |

A failed turn is stored with `status: "error"` (visible in the history), its tool executions stay logged, and it's left out when the history is replayed.

## 6. Example conversations with curl

Real responses from the Docker container with real Gemini (`docs/chatbot-verification.md`). The weather values are random.

**Create a conversation** (an optional `system_prompt`, e.g. `"Answer in French."`, is added to the app's own instructions):

```bash
curl -s -X POST localhost:8000/conversations -H 'Content-Type: application/json' -d '{}'
```
```json
{"id":"conv_e190b1750285","created_at":"2026-11-10T19:44:55.194137Z"}
```

**No tools needed:**

```bash
curl -s -X POST localhost:8000/conversations/conv_15ef53601ebd/messages \
  -H 'Content-Type: application/json' -d '{"content": "Hello"}'
```
```json
{"message":{"role":"assistant","content":"Hello! How can I help you today?"},"tools_used":[],"tokens_used":761}
```

**Two tools in one round:** `{"content": "What's the weather in Tokyo and what's 15% tip on $85?"}`

```json
{
  "message": {"role": "assistant", "content": "The current weather in Tokyo is sunny with a temperature of 12°C. A 15% tip on $85 is $12.75."},
  "tools_used": [
    {"tool": "weather", "input": {"location": "Tokyo"},
     "output": {"location": "Tokyo", "temperature": 12, "condition": "sunny", "humidity": 43},
     "success": true, "error": null, "execution_time_ms": 2},
    {"tool": "calculator", "input": {"expression": "85 * 0.15"}, "output": {"result": 12.75},
     "success": true, "error": null, "execution_time_ms": 2}
  ],
  "tokens_used": 1693
}
```

**Weather and time:** `{"content": "What's the weather and time in London?"}`

```json
{
  "message": {"role": "assistant", "content": "In London, it is currently 7:45 PM (19:45) and the weather is rainy with a temperature of 10°C."},
  "tools_used": [
    {"tool": "weather", "input": {"location": "London"},
     "output": {"location": "London", "temperature": 10, "condition": "rainy", "humidity": 70},
     "success": true, "error": null, "execution_time_ms": 2},
    {"tool": "datetime", "input": {"operation": "current", "timezone": "Europe/London"},
     "output": {"result": "2026-11-10T19:45:01.773859+00:00"}, "success": true, "error": null, "execution_time_ms": 7}
  ],
  "tokens_used": 1946
}
```

**A tool error, explained:** `{"content": "What is 1/0?"}`

```json
{
  "message": {"role": "assistant", "content": "I cannot calculate that because it is a division by zero, which is mathematically undefined."},
  "tools_used": [
    {"tool": "calculator", "input": {"expression": "1/0"}, "output": null,
     "success": false, "error": "Division by zero", "execution_time_ms": 1}
  ],
  "tokens_used": 2135
}
```

**History:** later in the same conversation, `{"content": "What did you calculate earlier?"}`

```json
{"message":{"role":"assistant","content":"Earlier, I performed the following calculations for you:\n\n1.  **2 + 2**: The result was 4.\n2.  **25% of 180**: The result was 45.\n3.  **1 / 0**: This resulted in an error because division by zero is mathematically undefined."},"tools_used":[],"tokens_used":1317}
```

**Database:** `{"content": "How many orders were placed last month?"}`

```json
{
  "message": {"role": "assistant", "content": "There were 40 orders placed last month."},
  "tools_used": [
    {"tool": "database_query",
     "input": {"sql": "SELECT count(*) FROM orders WHERE order_date >= date('now', 'start of month', '-1 month') AND order_date < date('now', 'start of month')"},
     "output": {"columns": ["count(*)"], "rows": [[40]], "row_count": 1, "truncated": false},
     "success": true, "error": null, "execution_time_ms": 9}
  ],
  "tokens_used": 1939
}
```

**A write is rejected by the tool:** `{"content": "Use the database_query tool to run exactly this SQL and tell me the result: DELETE FROM orders"}`

```json
{
  "message": {"role": "assistant", "content": "The database tool is configured for read-only access and only permits `SELECT` statements. Therefore, I cannot execute the `DELETE` command you provided."},
  "tools_used": [
    {"tool": "database_query", "input": {"sql": "DELETE FROM orders"}, "output": null,
     "success": false, "error": "Query rejected: only one read-only SELECT is allowed", "execution_time_ms": 3}
  ],
  "tokens_used": 1633
}
```

**Managing conversations:**

```bash
curl -s localhost:8000/conversations                              # list, newest first
curl -s localhost:8000/conversations/conv_15ef53601ebd            # full history with tools_used
curl -s -X POST localhost:8000/conversations/conv_15ef53601ebd/reset   # {"id": ..., "message_count": 0}
curl -s -X DELETE localhost:8000/conversations/conv_15ef53601ebd       # 204
curl -s localhost:8000/tools                                      # tool definitions
curl -s localhost:8000/health                                     # {"status": "ok"}
```

An empty message gives 422, and an unknown conversation id gives 404.

## 7. Key decisions

**Tool selection.** The LLM decides, with tool choice `AUTO`. It decides from two things: each tool's description, which says what the tool does and when to use it, and fixed app instructions in the system prompt ("Use a tool whenever it gives a more accurate or more current answer than you can"). Testing with real Gemini showed it sometimes answered "What is 1/0?" from its own knowledge. The calculator description and the instructions now say to use the calculator for any math, even impossible math; after that, 25 of 25 runs used it. Questions that need no tool still get none.

**Multiple tools.** Several tools in one round run in parallel, and all results go back in one message in the order requested. Chains take more rounds, up to 5; then the LLM must answer in text. See section 4.

**Tool errors.** Every tool problem becomes an error result that the LLM explains, the client sees, and the log keeps. LLM failures end the turn with a 502 and mark it `error`. See section 5.

**Security.**
- *Calculator:* Python's `ast` parses the expression, and only numbers, the listed operators, functions and constants are allowed. `eval`/`exec` are never used, so `__import__('os')` is just an invalid expression. Limits stop huge calculations: 200 characters, exponents up to 1000, nesting depth 20, and results must be finite numbers (`1e999` gives "Result too large").
- *Database:* three layers. The sample data is a separate file from the conversations. The connection is opened read-only (`mode=ro`). An SQLite authorizer allows only reading, so `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ATTACH` and `PRAGMA` are all rejected by SQLite itself. On top of that: one statement per call, at most 100 rows, and a 2-second limit per query.
- *All tools:* every input is checked against the tool's JSON Schema, and unknown fields are rejected, before the tool runs. Each round has a timeout.
- *Other:* messages are limited to 10,000 characters and system prompts to 4,000. The API key comes from the environment only. Tool output is passed to the LLM as data, and search is a mock.

**Context management.** History is stored in SQLite, and every turn replays it to the LLM: user messages, the LLM's tool calls and their results, and the final answers. Long chats send only the **last 20 turns**, cut at a turn boundary so a tool call never loses its result. Older turns stay visible in `GET /conversations/{id}` but are no longer sent. The system prompt never changes during a conversation (it contains no date), so every turn starts from the same instructions. Failed turns are not replayed.

**Separation of concerns.** The code is split into layers, and imports go one way only: `api → services → (tools, llm, models)`. `app/main.py` connects them. `tests/test_architecture.py` fails if a forbidden import appears.

| Layer | Files | Job |
|---|---|---|
| HTTP | `app/api/routes.py` | Parse the request, call a service, return the response |
| Validation | `app/schemas.py` | Request and response shapes |
| Business rules | `app/services/` | Conversations, and the tool loop of one turn |
| LLM | `app/llm/` | The only code that knows Gemini: translates messages to and from a neutral `LLMResult` |
| Tools | `app/tools/` | One file per tool, plus the registry and the executor |
| Data | `app/db.py`, `app/models.py` | Tables and sessions |
| Wiring | `app/main.py`, `app/config.py` | Settings, building the objects, error → HTTP status |

This paid off during the project: switching the LLM provider from Claude to Gemini changed `app/llm/` plus a few lines of settings, wiring and the tool registry. The services and the HTTP layer didn't change. Adding a tool touches only `app/tools/`.

## 8. Known limitations and what I'd do with more time

- Weather and web search are mocks, as the assignment allows. Weather values are random, so they ignore city and season.
- Long chats are trimmed, not summarized; with more time, old turns would be summarized.
- Not built: streaming responses, a real weather API, custom tool registration, tool usage analytics, rate limiting per tool.

The project was built spec-first and test-first. Requirements, architecture, spec, tasks and the verification report are in `docs/`.
