import uuid
from datetime import date

from sqlalchemy import select

from app.models import Event


def test_event_persists_with_generated_id_and_timestamp(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.commit()

    fetched = db_session.execute(select(Event)).scalar_one()

    assert isinstance(fetched.id, uuid.UUID)
    assert fetched.date == date(2026, 9, 1)
    assert fetched.created_at is not None
