"""HTTP routes. Only HTTP work lives here; the rules are in app/services.

These are plain `def` routes (not `async def`), so FastAPI runs them in a
thread pool and blocking work never freezes the server.
"""

from collections.abc import Callable, Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import schemas
from app.models import Message
from app.services import chat
from app.services import conversations as service

router = APIRouter()


def get_session(request: Request) -> Iterator[Session]:
    """One database session per request, always closed afterwards."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_clock(request: Request) -> Callable[[], datetime]:
    return request.app.state.clock


def get_llm(request: Request):
    return request.app.state.llm


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/conversations", status_code=201, response_model=schemas.ConversationCreated)
def create_conversation(
    body: schemas.CreateConversationRequest | None = None,
    session: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
):
    system_prompt = body.system_prompt if body else None
    return service.create_conversation(session, clock, system_prompt)


@router.get("/conversations", response_model=schemas.ConversationList)
def list_conversations(session: Session = Depends(get_session)):
    return {
        "conversations": [
            {
                "id": conversation.id,
                "created_at": conversation.created_at,
                "last_message_at": conversation.last_message_at,
                "message_count": count,
            }
            for conversation, count in service.list_conversations(session)
        ]
    }


def message_to_dict(message: Message) -> dict:
    data = {"role": message.role, "content": message.content, "created_at": message.created_at}
    if message.role == "assistant":
        data.update(
            status=message.status,
            tools_used=message.tools_used,
            tokens_used=message.tokens_used,
        )
    return data


@router.get(
    "/conversations/{conversation_id}",
    response_model=schemas.ConversationDetail,
    response_model_exclude_unset=True,  # user messages carry no assistant-only keys
)
def get_conversation(conversation_id: str, session: Session = Depends(get_session)):
    conversation = service.get_conversation(session, conversation_id)
    return {
        "id": conversation.id,
        "system_prompt": conversation.system_prompt,
        "created_at": conversation.created_at,
        "messages": [message_to_dict(message) for message in conversation.messages],
    }


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, session: Session = Depends(get_session)):
    service.delete_conversation(session, conversation_id)


@router.post("/conversations/{conversation_id}/reset", response_model=schemas.ConversationReset)
def reset_conversation(conversation_id: str, session: Session = Depends(get_session)):
    conversation = service.reset_conversation(session, conversation_id)
    return {"id": conversation.id, "message_count": len(conversation.messages)}


@router.post("/conversations/{conversation_id}/messages", response_model=schemas.SendMessageResponse)
def send_message(
    conversation_id: str,
    body: schemas.SendMessageRequest,  # validated before the route runs (FR-9: 422 before 404)
    session: Session = Depends(get_session),
    clock: Callable[[], datetime] = Depends(get_clock),
    llm=Depends(get_llm),
):
    assistant = chat.send_message(session, clock, llm, conversation_id, body.content)
    return {
        "message": {"role": "assistant", "content": assistant.content},
        "tools_used": assistant.tools_used,
        "tokens_used": assistant.tokens_used,
    }
