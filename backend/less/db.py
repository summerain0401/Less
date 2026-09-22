from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from less.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    result = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):

        @event.listens_for(result, "connect")
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return result


def ensure_parent(url: str) -> None:
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)


ensure_parent(settings().database_url)
engine = make_engine(settings().database_url)
Session = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    from less import models  # noqa: F401

    Base.metadata.create_all(engine)
