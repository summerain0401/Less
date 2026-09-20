import os
import subprocess
import uuid

import psycopg
import pytest
from less import db
from less.config import ROOT, settings
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


@pytest.fixture(scope="session")
def test_database():
    url = os.environ.get("LESS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set LESS_TEST_DATABASE_URL to run PostgreSQL integration tests")
    parsed = make_url(url)
    name = "less_test_" + uuid.uuid4().hex[:12]
    admin_url = parsed.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    test_url = parsed.set(database=name).render_as_string(hide_password=False)
    env = {**os.environ, "LESS_DATABASE_URL": test_url}
    subprocess.run(
        [str(ROOT / ".venv/bin/alembic"), "upgrade", "head"], cwd=ROOT, env=env, check=True
    )
    old_engine = db.engine
    test_engine = create_engine(test_url)
    db.engine = test_engine
    db.Session.configure(bind=test_engine)
    yield test_engine
    db.Session.configure(bind=old_engine)
    db.engine = old_engine
    test_engine.dispose()
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def database(test_database, tmp_path, monkeypatch):
    from less.db import Base

    with test_database.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    monkeypatch.setattr(settings(), "data_dir", tmp_path)
    return test_database
