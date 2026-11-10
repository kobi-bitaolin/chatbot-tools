"""FastAPI application factory.

Run with: uvicorn app.main:create_app --factory
Tests call create_app(settings) with temporary folders.
"""

from fastapi import FastAPI

from app.config import Settings
from app.db import Base, make_engine, make_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.app_db_path)
    Base.metadata.create_all(engine)

    app = FastAPI(title="Chatbot Tools API")
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app
