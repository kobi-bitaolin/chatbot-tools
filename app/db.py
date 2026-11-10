"""Database engine and session setup for the app database (app.db)."""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    """Parent class of all ORM models."""


class UtcDateTime(TypeDecorator):
    """A datetime column that is always UTC.

    SQLite has no time zones, so it would hand back naive datetimes. This type
    refuses naive datetimes on the way in and returns UTC-aware ones on the way out.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime: use a timezone-aware UTC datetime")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


def make_engine(db_path: Path) -> Engine:
    # check_same_thread=False: FastAPI runs plain `def` routes in a thread pool,
    # so a connection may be used by a different thread than the one that made it.
    # Each request still gets its own session, so no session is shared.
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
