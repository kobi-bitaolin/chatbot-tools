"""Conversation business rules: create, list, get, delete, reset.

No HTTP in here, so these functions can be tested and reused without a server.
"""

import secrets
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, Message


class ConversationNotFoundError(Exception):
    """The requested conversation id does not exist."""


def create_conversation(
    session: Session, clock: Callable[[], datetime], system_prompt: str | None
) -> Conversation:
    conversation = Conversation(
        id="conv_" + secrets.token_hex(6),  # 12 lowercase hex characters
        system_prompt=system_prompt,
        created_at=clock(),
        last_message_at=None,
    )
    session.add(conversation)
    session.commit()
    return conversation


def list_conversations(session: Session) -> list[tuple[Conversation, int]]:
    """All conversations with their message counts, newest first."""
    statement = (
        select(Conversation, func.count(Message.id))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .group_by(Conversation.id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
    )
    return [(conversation, count) for conversation, count in session.execute(statement)]


def get_conversation(session: Session, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise ConversationNotFoundError(conversation_id)
    return conversation


def delete_conversation(session: Session, conversation_id: str) -> None:
    """Delete the conversation; its messages and tool executions go with it."""
    session.delete(get_conversation(session, conversation_id))
    session.commit()


def reset_conversation(session: Session, conversation_id: str) -> Conversation:
    """Remove all messages and tool executions; keep the conversation and its prompt."""
    conversation = get_conversation(session, conversation_id)
    conversation.messages.clear()  # delete-orphan removes them, and their executions
    conversation.last_message_at = None  # an empty conversation has no last message
    session.commit()
    return conversation
