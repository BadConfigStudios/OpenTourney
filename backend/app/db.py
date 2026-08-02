from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_settings


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url)


def get_db_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
