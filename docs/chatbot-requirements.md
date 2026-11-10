# Chatbot Tools: Requirements

- **Source (S1):** `chatbot-tool.md` (line numbers in brackets, e.g. `S1:40`)
- **Stage:** 1, requirements intake
- **Status:** Draft, awaiting approval
- **Date:** 2026-11-10

Provisional IDs (`REQ-n`) are used here. The numbered `FR`/`NFR` spec is written in stage 3.

## 1. Problem and goal

Build a chatbot HTTP API that uses LLM function calling to run tools (calculator, web search, weather, database query, date/time) and answer questions that pure text generation cannot (S1:11). The evaluators judge whether you understand function calling, tool interface design, graceful tool error handling, and whether the product works and is well structured (S1:26-30). You must explain every line in a follow-up interview (S1:32).

**Actors:** the API client (a user sending messages through curl or another tool), the LLM provider, and the evaluator who reviews the repo.

## 2. Requirements

### 2.1 Chat API (S1:38-43)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-1 | Send a message to a conversation and receive the assistant's response | Must | S1:40, S1:225-241 |
| REQ-2 | Keep conversation history and send it to the LLM on each turn | Must | S1:41 |
| REQ-3 | Support multi-turn conversations, where later answers can use earlier messages | Must | S1:42 |
| REQ-4 | Clear/reset a conversation | Must | S1:43 |

### 2.2 Tools (S1:45-55, S1:168-219)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-5 | **Calculator**: input is an expression string, output is a number. Examples: `"2 + 2"`→4, `"sqrt(16)"`→4, `"sin(3.14159/2)"`→1, `"100 * (1 + 0.05)^10"`→162.89 (`^` means power). Errors: invalid expression, division by zero | Must | S1:51, S1:170-181 |
| REQ-6 | **Web search**: input is a query string, output is a list of results, each with `title`, `snippet`, `url`. Mock (predefined results for common queries) or a real API | Must* | S1:52, S1:183-190 |
| REQ-7 | **Weather**: input is a location string, output is `temperature`, `condition`, `humidity`. Mock (random but realistic values) or a real API | Must* | S1:53, S1:192-199 |
| REQ-8 | **Database query**: input is a natural-language question about sample data, output is the query results. Sample tables are `products`, `users`, `orders`. Example: "How many orders were placed last month?"→`{"count": 142}` | Must* | S1:54, S1:201-208 |
| REQ-9 | **Date/time**: operations are `current` (current date/time), `convert` (between timezones), `calculate` (add/subtract from a date). Output is a formatted date/time | Must* | S1:55, S1:210-219 |
| REQ-10 | At least 4 tools are implemented | Must | S1:344 |
| REQ-11 | Every tool has a definition in the given format: `name`, `description`, `parameters` (JSON Schema with `properties` and `required`) | Must | S1:102-119 |
| REQ-12 | List available tools: `GET /tools` returns `{"tools": [{"name", "description"}]}` | Must | S1:270-280 |

\* The assignment lists 5 tools to implement (S1:49) but only requires "at least 4" (S1:344). See G4.

### 2.3 Tool execution flow (S1:57-63)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-13 | The user sends a message, and the LLM decides whether tools are needed | Must | S1:59-60 |
| REQ-14 | If tools are needed, execute them, feed the results back to the LLM, and let the LLM write the final response | Must | S1:61-62 |
| REQ-15 | Return the response together with tool usage info (`tools_used`) | Must | S1:63 |
| REQ-16 | Each tool result follows the format `{tool, input, output, success, execution_time_ms}` | Must | S1:121-131 |

### 2.4 Conversation management (S1:65-70)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-17 | Create a conversation: `POST /conversations` with an optional `system_prompt`, returns `{id, created_at}` (example id `conv_123`) | Must | S1:67, S1:243-254 |
| REQ-18 | List conversations | Must | S1:68 |
| REQ-19 | Get conversation history: `GET /conversations/{id}` returns `{id, messages: [{role, content, tools_used?}], created_at}` | Must | S1:69, S1:256-268 |
| REQ-20 | Delete a conversation | Must | S1:70 |

### 2.5 Message and response formats (S1:133-164, S1:225-241)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-21 | Send message request body: `{"content": "..."}` to `POST /conversations/{id}/messages` | Must | S1:227-230 |
| REQ-22 | Chat response: `{message: {role: "assistant", content}, tools_used: [{tool, input, output}], tokens_used}` | Must | S1:142-164 |

### 2.6 Data model (S1:284-309)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-23 | **Conversation**: unique id, optional system prompt, created at, last message at | Must | S1:288-292 |
| REQ-24 | **Message**: conversation relation, role (`user`/`assistant`/`system`), content, tools used (JSON), tokens used, created at | Must | S1:294-300 |
| REQ-25 | **ToolExecution**: message relation, tool name, input parameters, output/result, success flag, error message (if failed), execution time | Must | S1:302-309 |
| REQ-26 | Tool execution logging: every tool run is recorded | Must | S1:346 |

### 2.7 Edge cases (S1:325-333)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-27 | No tools needed: respond directly | Must | S1:327 |
| REQ-28 | Tool returns an error: inform the user gracefully | Must | S1:328 |
| REQ-29 | Multiple tools needed: execute all of them and combine the results | Must | S1:329 |
| REQ-30 | Invalid tool parameters: handle validation errors | Must | S1:330 |
| REQ-31 | Tool execution timeout: return partial results or an error | Must | S1:331 |
| REQ-32 | Recursive tool calls: prevent infinite loops | Must | S1:332 |
| REQ-33 | Empty conversation: handle the first message properly | Must | S1:333 |

### 2.8 Technical requirements (S1:337-368)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-34 | Python 3.11+ | Must | S1:341 |
| REQ-35 | Web framework of your choice | Must | S1:342 |
| REQ-36 | LLM integration with function calling | Must | S1:343 |
| REQ-37 | Containerized: `Dockerfile` + `docker-compose.yml` | Must | S1:347 |
| REQ-38 | At least 6 meaningful tests: basic chat without tools, single tool, multiple tools, tool error handling, conversation history, tool execution logging | Must | S1:348-354 |
| REQ-39 | Streaming responses | Should | S1:358 |
| REQ-40 | Tool execution timeouts | Should | S1:359 |
| REQ-41 | Input validation for tools | Should | S1:360 |
| REQ-42 | Token usage tracking | Should | S1:361 |
| REQ-43 | Custom tool registration | Nice | S1:365 |
| REQ-44 | Tool usage analytics | Nice | S1:366 |
| REQ-45 | Conversation summarization for long chats | Nice | S1:367 |
| REQ-46 | Rate limiting per tool | Nice | S1:368 |

Note: REQ-40 and REQ-41 are "Should" items, but edge cases REQ-30 and REQ-31 require handling invalid parameters and timeouts anyway. In practice they are needed.

### 2.9 Documentation and submission (S1:313-321, S1:372-413)
| ID | Requirement | Priority | Source |
|---|---|---|---|
| REQ-47 | Git repo with `README.md`, `AI_USAGE.md`, `docker-compose.yml`, `Dockerfile`, `requirements.txt`, app code, tests | Must | S1:374-385 |
| REQ-48 | README covers: how to run, how to run tests, available tools, how multiple tool calls are handled, how tool errors are handled, example conversations with curl | Must | S1:387-395 |
| REQ-49 | README documents 5 decisions: tool selection, multiple tools, tool errors, security (e.g. dangerous calculations), context management for long conversations | Must | S1:313-321 |
| REQ-50 | `AI_USAGE.md` in the exact template: Tools I Used, What Helped Most, What I Had to Fix, What AI Struggled With | Must | S1:397-413 |

## 3. Constraints
- Python 3.11+, any web framework, an LLM with function calling, Docker (S1:341-347).
- Security against malicious tool use must be designed and explained (S1:320).
- AI tools are allowed, but every line must be understood (S1:19, S1:32).
- Suggested build order: basic chat → calculator → tool-calling logic → more tools → errors (S1:419-424).

## 4. Out of scope (as far as the assignment says)
- A user interface. The assignment asks only for an API.
- Authentication and user accounts. Not mentioned.
- Production cloud deployment. The submission is a Git repo with Docker (S1:374).

## 5. Gaps and conflicts in the assignment

| # | Gap | Recommendation |
|---|---|---|
| G1 | No endpoint paths are given for list conversations, delete conversation, or clear/reset (S1:43, S1:68, S1:70) | `GET /conversations`, `DELETE /conversations/{id}`, `POST /conversations/{id}/reset` (deletes messages, keeps the conversation and its system prompt) |
| G2 | `tokens_used` is in the chat response format (S1:162) but missing from the send-message example (S1:232-240) | Always include `tokens_used` |
| G3 | `tools_used` items in the chat response (S1:151-160) omit `success` and `execution_time_ms`, which the tool response format has (S1:127-129) | Use the full tool response format in `tools_used`, plus `error` when it failed |
| G4 | The assignment lists 5 tools (S1:49) but requires at least 4 (S1:344) | Build all 5. The extra one is cheap and shows completeness |
| G5 | Web search and weather can each be mock or real (S1:188-189, S1:197-198) | Mocks: no extra API keys, tests are repeatable, and the evaluator can run it easily |
| G6 | Database input is natural language (S1:204), but how it becomes a query is not specified, and letting the LLM write raw SQL is a security risk (S1:320) | Decide in stage 2 (architecture). Sample data must include orders with dates so "last month" works |
| G7 | No numbers for the tool timeout, the maximum number of tool-call rounds (infinite-loop guard), or the length limit for long conversations | Set in stage 2/3. Suggested start: 5 s per tool, 5 rounds, keep the last N messages |
| G8 | Calculator rounding is unclear: `"sin(3.14159/2)"`→1 and `162.89` look rounded, while `17.0` is shown as a float (S1:131, S1:177-179) | Return the full-precision number. Tests compare approximately. The LLM rounds when it writes the answer |
| G9 | Edge case 5 (S1:331) allows "partial results or an error" | When several tools run and one times out, return the others and mark the timed-out one as failed |
| G10 | Persistence across restarts is not stated | Store in SQLite on a Docker volume, so history survives a restart |
| G11 | Which Should/Nice items to build | See question Q1 |
| G12 | The conversation id format is only shown by example (`conv_123`, S1:251) | `conv_` + a random unique suffix |
| G13 | Message role `system` (S1:296): it's unclear whether the system prompt is stored as a message | Store it on the Conversation and send it to the LLM as the system prompt. The history endpoint shows only user/assistant messages |
| G14 | The project folder is not a Git repo, but the submission must be a Git repo (S1:374) and the workflow commits each task | See question Q4 |

## 6. Assumptions
- A1: One API client and no authentication, since none is mentioned.
- A2: Mock data is acceptable to the evaluators, since the assignment explicitly allows it (S1:52-53).

## 7. Decided answers
| # | Question | Answer | Date |
|---|---|---|---|
| | *(filled in after your answers)* | | |

## 8. Open questions
- Q1-Q4, asked in chat. G1-G3, G4, G8-G10, G12, G13 have recommendations waiting for your OK.
- G6 and G7 move to stage 2 (they are design choices, not requirement gaps).
