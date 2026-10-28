import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://studio:studio@localhost:5433/studio"


def database_url() -> str:
    return os.environ.get("STUDIO_DATABASE_URL", DEFAULT_URL)


_engine = None
_Session = None


def engine():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(database_url(), pool_pre_ping=True)
        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """For tests that point the app at another database."""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = _Session = None


def get_session():
    """One session per request (FastAPI dependency)."""
    engine()
    with _Session() as session:
        yield session


@contextmanager
def session_scope():
    engine()
    with _Session() as session:
        yield session
