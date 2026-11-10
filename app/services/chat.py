"""The chat service (orchestrator): one user message is one turn (architecture §4).

This is the only code that writes to the app database during a turn.
A turn can have several LLM rounds: while the LLM asks for tools, the tools
run and their results go back to it, until it gives a final answer (FR-12).
After MAX_TOOL_ROUNDS tool rounds, one last call with tool choice "none"
makes the LLM answer in text (FR-15). T-12 adds the other stop reasons and
LLM errors.
"""

import json
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.llm.result import LLMResult
from app.models import Message, ToolExecution
from app.services.conversations import get_conversation
from app.tools.executor import ToolCall, ToolExecutor, ToolResult
from app.tools.registry import ToolRegistry

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."
MAX_HISTORY_TURNS = 20  # FR-23
MAX_TOOL_ROUNDS = 5  # FR-15
LIMIT_ERROR = "Tool call limit reached"


def build_app_instructions(tool_names: list[str]) -> str:
    """D0: fixed text plus the registered tool names (NFR-12).

    The names come from the registry, so adding a tool never means editing
    this service. Each tool's description tells the LLM when to use it.
    Nothing here changes between calls (no dates), so the prompt stays
    byte-identical (FR-24).
    """
    return (
        "You are the assistant behind a chat API that can call tools. "
        "Use a tool whenever it gives a more accurate or more current answer than you can. "
        # Risk R1 (spec v0.7): the model skipped the calculator for "What is 1/0?".
        "Never answer a math question from your own knowledge, even a trivial or "
        "impossible one such as division by zero: call the calculator. "
        f"Available tools: {', '.join(tool_names)}. "
        "If a tool returns an error, explain the problem to the user in plain words."
    )


def build_system_prompt(tool_names: list[str], system_prompt: str | None) -> str:
    """FR-24: app instructions, a blank line, then the client's prompt or the default."""
    return build_app_instructions(tool_names) + "\n\n" + (system_prompt or DEFAULT_SYSTEM_PROMPT)


def build_history(messages: list[Message]) -> list[dict]:
    """FR-21, FR-23: the earlier turns, ready to send before the new user message.

    `messages` is the conversation in order. A turn is a user message plus
    the assistant message right after it; only `complete` turns are replayed
    (a failed turn is skipped, user message included). Only the last
    MAX_HISTORY_TURNS turns are kept, so the cut is always at a turn
    boundary and the first message sent is a user message.
    """
    turns = [
        (user, assistant)
        for user, assistant in zip(messages, messages[1:])
        if user.role == "user" and assistant.role == "assistant" and assistant.status == "complete"
    ]
    history = []
    for user, assistant in turns[-MAX_HISTORY_TURNS:]:
        history.append({"role": "user", "content": user.content})
        # The tool rounds: every stored message except the final answer,
        # with thinking removed (FR-22: it is only passed back within its turn).
        for message in assistant.llm_blocks[:-1]:
            blocks = [b for b in message["content"] if b["type"] != "thinking"]
            history.append({"role": message["role"], "content": blocks})
        # The final answer as plain text, the same for every stop reason.
        history.append({"role": "assistant", "content": assistant.content})
    return history


def tool_result_block(call_id: str, result: ToolResult) -> dict:
    """One result for the LLM, paired with its call by `tool_use_id` (FR-13, FR-16)."""
    if result.success:
        return {"type": "tool_result", "tool_use_id": call_id, "content": json.dumps(result.output)}
    return {"type": "tool_result", "tool_use_id": call_id, "content": result.error, "is_error": True}


def send_message(
    session: Session,
    clock: Callable[[], datetime],
    llm,
    registry: ToolRegistry,
    executor: ToolExecutor,
    conversation_id: str,
    content: str,
) -> Message:
    """Run one turn and return the finished assistant message."""
    conversation = get_conversation(session, conversation_id)  # 404 if missing
    history = build_history(conversation.messages)  # before this turn's messages are added

    # Save the user message and a "pending" assistant message first, so the
    # turn is visible (and its tool runs can be linked) even if the LLM fails.
    now = clock()
    conversation.messages.append(
        Message(role="user", content=content, created_at=now)
    )
    assistant = Message(role="assistant", content="", status="pending", created_at=clock())
    conversation.messages.append(assistant)
    conversation.last_message_at = assistant.created_at
    session.commit()

    system = build_system_prompt(registry.names(), conversation.system_prompt)
    tools = registry.api_definitions()
    # FR-20, FR-21: earlier turns first, then the new user message.
    messages = history + [{"role": "user", "content": content}]
    turn_blocks: list[dict] = []  # everything after the user message, for llm_blocks
    tools_used: list[dict] = []
    tokens_used = 0
    tool_rounds = 0
    tool_choice = {"type": "auto"}

    while True:
        result: LLMResult = llm.complete(
            system=system, messages=messages, tools=tools, tool_choice=tool_choice
        )
        tokens_used += result.input_tokens + result.output_tokens  # FR-19
        # All blocks go back unchanged (thinking included), so the LLM sees its own turn.
        assistant_turn = {"role": "assistant", "content": result.blocks}
        turn_blocks.append(assistant_turn)
        # Stop on a final answer, and always after the forced last call (FR-15).
        if result.stop_reason != "tool_use" or tool_choice["type"] == "none":
            break

        calls = [ToolCall(c.name, c.input) for c in result.tool_calls]
        if tool_rounds < MAX_TOOL_ROUNDS:
            results = executor.run_round(calls)
            tool_rounds += 1
        else:
            # FR-15: these calls don't run. Each gets the limit error, and the
            # next call is the last one, with tools turned off.
            results = [limit_result(call) for call in calls]
            tool_choice = {"type": "none"}
        log_round(session, clock, assistant, results)  # FR-34
        tools_used += [r.to_dict() for r in results]
        # FR-13: ONE user message with every result, in the order they were asked for.
        tool_turn = {
            "role": "user",
            "content": [tool_result_block(c.id, r) for c, r in zip(result.tool_calls, results)],
        }
        turn_blocks.append(tool_turn)
        messages += [assistant_turn, tool_turn]

    # FR-11 / FR-26 (end_turn): the final answer is the last response's text.
    # The other stop reasons (refusal, max_tokens, ...) come in T-12.
    assistant.content = result.text
    assistant.status = "complete"
    assistant.tools_used = tools_used
    assistant.tokens_used = tokens_used
    assistant.llm_blocks = turn_blocks
    conversation.last_message_at = clock()  # FR-7
    session.commit()
    return assistant


def limit_result(call: ToolCall) -> ToolResult:
    """FR-15: the result for a call that was not run because of the round limit."""
    return ToolResult(
        tool=call.name,
        input=call.input,
        output=None,
        success=False,
        error=LIMIT_ERROR,
        execution_time_ms=0,
    )


def log_round(
    session: Session, clock: Callable[[], datetime], assistant: Message, results: list[ToolResult]
) -> None:
    """FR-34: one ToolExecution row per call, saved right after its round.

    Runs on the request thread, never in the tool threads (SQLAlchemy
    sessions are not thread-safe, architecture §3.2).
    """
    for r in results:
        assistant.tool_executions.append(
            ToolExecution(
                tool_name=r.tool,
                input=r.input,
                output=r.output,
                success=r.success,
                error_message=r.error,
                execution_time_ms=r.execution_time_ms,
                created_at=clock(),
            )
        )
    session.commit()
