"""Database engine and session setup for the app database (app.db)."""

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Parent class of all ORM models."""


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
