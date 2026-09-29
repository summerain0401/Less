from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
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

    source_keys_existed = inspect(engine).has_table("source_keys")
    fts_existed = inspect(engine).has_table("brief_fts")
    Base.metadata.create_all(engine)
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS brief_fts USING "
            "fts5(brief_id UNINDEXED, title, what_happened, tokenize='trigram')"
        ))
        connection.execute(text("""
            CREATE TRIGGER IF NOT EXISTS brief_fts_insert AFTER INSERT ON briefs BEGIN
              INSERT INTO brief_fts(rowid, brief_id, title, what_happened)
              VALUES (new.rowid, new.id, new.title, new.what_happened);
            END
        """))
        connection.execute(text("""
            CREATE TRIGGER IF NOT EXISTS brief_fts_update AFTER UPDATE OF title, what_happened ON briefs BEGIN
              DELETE FROM brief_fts WHERE rowid = old.rowid;
              INSERT INTO brief_fts(rowid, brief_id, title, what_happened)
              VALUES (new.rowid, new.id, new.title, new.what_happened);
            END
        """))
        connection.execute(text("""
            CREATE TRIGGER IF NOT EXISTS brief_fts_delete AFTER DELETE ON briefs BEGIN
              DELETE FROM brief_fts WHERE rowid = old.rowid;
            END
        """))
        if not fts_existed:
            connection.execute(text(
                "INSERT INTO brief_fts(rowid, brief_id, title, what_happened) "
                "SELECT rowid, id, title, what_happened FROM briefs"
            ))
        if not source_keys_existed:
            from less.dedup import url_key

            rows = connection.execute(text("SELECT id, url FROM sources")).all()
            if rows:
                connection.execute(
                    text("INSERT INTO source_keys(source_id, key) VALUES (:id, :key)"),
                    [{"id": row.id, "key": url_key(row.url)} for row in rows],
                )
