"""The chat service (orchestrator): one user message is one turn (architecture §4).

This is the only code that writes to the app database during a turn.
T-3 covers the turn without tools; the tool loop is added in T-7.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Message
from app.services.conversations import get_conversation

# D0: fixed app instructions. They never contain changing values (such as
# today's date), so the system prompt is byte-identical on every call (FR-24).
APP_INSTRUCTIONS = (
    "You are the assistant behind a chat API that can call tools. "
    "Use a tool whenever it gives a more accurate or more current answer than you can: "
    "the calculator for any arithmetic, web_search for current information, "
    "weather for the weather, database_query for questions about the store data, "
    "and datetime for dates, times and timezones. "
    "If a tool returns an error, explain the problem to the user in plain words."
)
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


def build_system_prompt(system_prompt: str | None) -> str:
    """FR-24: app instructions, a blank line, then the client's prompt or the default."""
    return APP_INSTRUCTIONS + "\n\n" + (system_prompt or DEFAULT_SYSTEM_PROMPT)


def send_message(
    session: Session,
    clock: Callable[[], datetime],
    llm,
    conversation_id: str,
    content: str,
) -> Message:
    """Run one turn and return the finished assistant message."""
    conversation = get_conversation(session, conversation_id)  # 404 if missing

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

    # FR-20: history replay is added in T-8, so for now the new user message
    # is the only message sent (which is exactly FR-20 for a first message).
    messages = [{"role": "user", "content": content}]
    response = llm.complete(
        system=build_system_prompt(conversation.system_prompt),
        messages=messages,
        tools=[],  # the 5 tool definitions are added in T-6
        tool_choice={"type": "auto"},
    )

    # FR-11: an answer without tools is the response's text blocks, joined.
    # The other stop reasons (tool_use, refusal, max_tokens, ...) come in T-7 and T-12.
    assistant.content = "".join(block.text for block in response.content if block.type == "text")
    assistant.status = "complete"
    assistant.tools_used = []
    assistant.tokens_used = response.usage.input_tokens + response.usage.output_tokens
    assistant.llm_blocks = [
        {
            "role": "assistant",
            "content": [block.model_dump(mode="json", exclude_none=True) for block in response.content],
        }
    ]
    conversation.last_message_at = clock()  # FR-7
    session.commit()
    return assistant
