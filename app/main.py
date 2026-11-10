"""FastAPI application factory.

Run with: uvicorn app.main:create_app --factory
Tests call create_app(settings) with temporary folders, and may pass a fake
clock and the fake LLM.
"""

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (importing registers the tables)
from app.api.routes import router
from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.llm.client import LLMClient
from app.services.conversations import ConversationNotFoundError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_app(
    settings: Settings | None = None,
    clock: Callable[[], datetime] | None = None,
    llm=None,
) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.app_db_path)
    Base.metadata.create_all(engine)

    app = FastAPI(title="Chatbot Tools API")
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)
    app.state.clock = clock or utc_now
    app.state.llm = llm or LLMClient(settings)  # the SDK client itself is created lazily

    @app.exception_handler(ConversationNotFoundError)
    def conversation_not_found(request: Request, error: ConversationNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})

    app.include_router(router)
    return app
