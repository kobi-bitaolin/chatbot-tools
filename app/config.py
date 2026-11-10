"""Application settings, read from environment variables.

Every setting has a safe default, so the app (and the tests) start without
any environment set. `.env.example` documents the variables.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Empty values (e.g. "LLM_MODEL=" copied from .env.example) mean "use the default".
    model_config = SettingsConfigDict(env_ignore_empty=True)

    # Only needed when the real LLM is called; the app starts without it.
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"

    # Folder holding app.db and sample.db (a Docker volume in production).
    data_dir: Path = Path("data")

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.db"
