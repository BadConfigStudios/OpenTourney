from app.db import get_db_session
from app.models import Event


def test_get_db_session_yields_a_working_session(migrated_engine, monkeypatch):
    monkeypatch.setattr("app.db.get_engine", lambda: migrated_engine)

    session_gen = get_db_session()
    session = next(session_gen)
    try:
        result = session.query(Event).count()
        assert isinstance(result, int)
    finally:
        session_gen.close()
