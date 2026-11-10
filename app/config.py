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
    gemini_api_key: str | None = None
    llm_model: str = "gemini-3.1-flash-lite"  # FR-36, D9
    tool_timeout_s: float = 5.0  # FR-18: one deadline per tool round

    # Folder holding app.db and sample.db (a Docker volume in production).
    data_dir: Path = Path("data")

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def sample_db_path(self) -> Path:
        return self.data_dir / "sample.db"
