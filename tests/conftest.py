import pytest
from fastapi.testclient import TestClient
from less import db
from less.api import app


@pytest.fixture
def client(tmp_path):
    test_engine = db.make_engine(f"sqlite:///{tmp_path / 'less-test.db'}")
    old_engine = db.engine
    db.engine = test_engine
    db.Session.configure(bind=test_engine)
    db.Base.metadata.create_all(test_engine)
    with TestClient(app) as test_client:
        yield test_client
    db.Session.configure(bind=old_engine)
    db.engine = old_engine
    test_engine.dispose()
