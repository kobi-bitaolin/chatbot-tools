"""ORM models: the S1 data model (Conversation, Message, ToolExecution).

Deleting a parent deletes its children through `cascade="all, delete-orphan"`.
SQLite ignores foreign keys unless asked, so we don't rely on the database
for this: SQLAlchemy does the deleting.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UtcDateTime


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # "conv_" + 12 hex chars
    system_prompt: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_message_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",  # insertion order; never ties
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    # none_as_null: Python None is stored as SQL NULL, not as the JSON text "null".
    tools_used: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    llm_blocks: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
    status: Mapped[str | None] = mapped_column(String)  # assistant only
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    tool_executions: Mapped[list["ToolExecution"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ToolExecution.id",
    )


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"))
    tool_name: Mapped[str] = mapped_column(String)
    input: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    success: Mapped[bool]
    error_message: Mapped[str | None] = mapped_column(Text)
    execution_time_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)

    message: Mapped[Message] = relationship(back_populates="tool_executions")
