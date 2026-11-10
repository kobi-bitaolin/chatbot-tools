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
from app.sample_data import seed_if_missing
from app.services.conversations import ConversationNotFoundError
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, default_registry


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_llm(settings: Settings, sdk=None) -> LLMClient:
    """Wiring: read the settings here, so the LLM client never imports config (NFR-12)."""
    return LLMClient(
        api_key=settings.gemini_api_key,
        model=settings.llm_model,
        sdk=sdk,
    )


def create_app(
    settings: Settings | None = None,
    clock: Callable[[], datetime] | None = None,
    llm=None,
    registry: ToolRegistry | None = None,
) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.app_db_path)
    Base.metadata.create_all(engine)
    clock = clock or utc_now
    # Seeded once with today's date (the clock's), then kept as it is (NFR-10).
    seed_if_missing(settings.sample_db_path, clock().date())

    app = FastAPI(title="Chatbot Tools API")
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)
    app.state.clock = clock
    app.state.llm = llm or build_llm(settings)  # the SDK client itself is created lazily
    app.state.registry = registry or default_registry(settings.sample_db_path)
    app.state.executor = ToolExecutor(app.state.registry)

    @app.exception_handler(ConversationNotFoundError)
    def conversation_not_found(request: Request, error: ConversationNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})

    app.include_router(router)
    return app
