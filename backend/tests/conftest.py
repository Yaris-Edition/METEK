from pathlib import Path
import sys
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from catalog_routes import router  # noqa: E402
from db import get_db, engine_for_url  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    url = 'sqlite:///' + str(tmp_path / 'sprint1.sqlite3')
    monkeypatch.setenv('DATABASE_URL', url)
    cfg = Config(str(BACKEND / 'alembic.ini'))
    command.upgrade(cfg, 'head')
    engine = engine_for_url(url)
    test_app = FastAPI()
    test_app.include_router(router)

    def db_dep():
        with Session(engine) as session:
            yield session

    test_app.dependency_overrides[get_db] = db_dep
    with TestClient(test_app) as client:
        yield engine, client
    engine.dispose()
    engine_for_url.cache_clear()
