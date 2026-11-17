"""Подключение каталога к PostgreSQL (SQLite — только для изолированных тестов)."""
from functools import lru_cache
from pathlib import Path
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def database_url() -> str:
    # CLI (seed, Alembic) работает без импорта app.py и его админки.
    # Переменные процесса приоритетнее локального файла.
    if not os.environ.get('DATABASE_URL'):
        cfg = Path(__file__).parent / 'config.env'
        if cfg.exists():
            for line in cfg.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        raise RuntimeError('DATABASE_URL не задан. Заполните backend/config.env и выполните alembic upgrade head.')
    return url


@lru_cache(maxsize=4)
def engine_for_url(url: str):
    kw = {'pool_pre_ping': True}
    if url.startswith('sqlite:'):
        kw['connect_args'] = {'check_same_thread': False}
    return create_engine(url, **kw)


def get_engine():
    return engine_for_url(database_url())


def get_db():
    """Одна SQLAlchemy Session на запрос; не коммитит GET-запросы."""
    with Session(get_engine()) as session:
        yield session
