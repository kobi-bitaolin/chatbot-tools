"""Request and response shapes of the API (Pydantic models)."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

MAX_SYSTEM_PROMPT_CHARS = 4000
MAX_CONTENT_CHARS = 10_000


class CreateConversationRequest(BaseModel):
    system_prompt: str | None = None

    @field_validator("system_prompt")
    @classmethod
    def clean_system_prompt(cls, value: str | None) -> str | None:
        """Strip spaces; an empty prompt means "use the default" (stored as None)."""
        if value is None:
            return None
        value = value.strip()
        if len(value) > MAX_SYSTEM_PROMPT_CHARS:
            raise ValueError(f"system_prompt must be at most {MAX_SYSTEM_PROMPT_CHARS} characters")
        return value or None


class ConversationCreated(BaseModel):
    id: str
    created_at: datetime


class ConversationSummary(BaseModel):
    id: str
    created_at: datetime
    last_message_at: datetime | None
    message_count: int


class ConversationList(BaseModel):
    conversations: list[ConversationSummary]


class MessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime
    # Assistant messages only. Routes build user messages without these keys,
    # and `response_model_exclude_unset` leaves them out of the JSON.
    status: str | None = None
    tools_used: list | None = None
    tokens_used: int | None = None


class ConversationDetail(BaseModel):
    id: str
    system_prompt: str | None
    created_at: datetime
    messages: list[MessageOut]


class ConversationReset(BaseModel):
    id: str
    message_count: int


class SendMessageRequest(BaseModel):
    # FR-9: stripped first, then 1-10,000 characters (422 otherwise).
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CONTENT_CHARS)
    ]


class AssistantReply(BaseModel):
    role: str
    content: str


class SendMessageResponse(BaseModel):
    message: AssistantReply
    tools_used: list
    tokens_used: int
