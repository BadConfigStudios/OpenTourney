# Phase 3 — Domain Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the first DB-backed domain model (`Event`/`Pod`/`Entry`/`Round`/`Match`), the `TournamentFormat` and `GameModule` plugin interfaces, and Alembic migrations, verified against the real `opentourney-staging` Percona Postgres cluster. Closes GitHub issue #3 (FR7–FR9, FR12 partial, NFR5).

**Architecture:** SQLAlchemy 2.0 declarative models (`Mapped`/`mapped_column` style) under `backend/app/models/`, one file per entity. Alembic manages schema as one migration per task/entity. `TournamentFormat` and `GameModule` are pure-Python ABC interfaces under `backend/app/formats/` and `backend/app/games/` — no DB tables, no cross-references between the two (NFR5). No FastAPI endpoints touch the DB yet (that's Phase 5); this phase only needs the schema to exist and be provably migratable.

**Tech Stack:** SQLAlchemy 2.0, Alembic, psycopg 3 (`psycopg[binary]`), Postgres 16 (Percona PG Operator, already deployed in Phase 2), testcontainers-python (integration tests), pytest.

## Global Constraints

- Python 3.12 (`backend/pyproject.toml` `requires-python`), SQLAlchemy 2.0 declarative style only (`Mapped[...]` / `mapped_column`, not legacy `Column`-only style).
- Postgres 16 — matches the Percona PGCluster already deployed (`charts/opentourney/values.yaml` `percona.pgVersion: "16"`). Use `postgresql.dialects` types (`UUID`, `JSONB`) since this project targets Postgres only, no other DB backend.
- No hardcoded secrets/credentials — `DATABASE_URL` comes from the environment only, never a literal connection string with embedded credentials in code.
- `badconfig-runners` CI already has a working docker daemon (confirmed via `.github/workflows/ci.yml`'s `docker-build` job) — testcontainers-based integration tests run there with zero CI YAML changes.
- TDD (RED → GREEN → REFACTOR): write the failing test, confirm it fails, write minimal code to pass, confirm it passes, refactor if needed, then commit test + implementation + migration together in one commit.
- Commits: Conventional Commits format, trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`, stage files by exact name (never `-A`/`.`).
- `Event` has **no** `modality` field (in-person only for v1 — DECISIONS.md 2026-07-19 "Online modality excluded from MVP1 entirely").
- `Pod.event_id` has **no** uniqueness constraint — schema supports many pods per event even though v1's API/UI (Phase 5) constrains to one (DECISIONS.md 2026-07-19 "`Pod` kept in schema, cardinality constrained in v1").
- `TournamentFormat` and `GameModule` interfaces must stay fully decoupled (NFR5) — neither module imports or references the other.
- One PR for this whole phase, description says `Closes #3`.

---

### Task 1: Data-access foundation + `Event` model

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/event.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_create_event.py`
- Create: `backend/tests/integration/conftest.py`
- Test: `backend/tests/integration/test_event_model.py`

**Interfaces:**
- Produces: `app.models.Base` (SQLAlchemy `DeclarativeBase`), `app.models.base.UUIDPrimaryKeyMixin` (gives `id: Mapped[uuid.UUID]`), `app.models.base.TimestampMixin` (gives `created_at: Mapped[datetime]`), `app.models.Event` (columns: `id`, `date: Mapped[date]`, `created_at`). Fixtures `db_session` and `migrated_engine` (session-scoped) in `tests/integration/conftest.py`, usable by every later integration test in this phase without modification.
- Consumes: nothing from earlier tasks (first task).

- [ ] **Step 1: Add DB dependencies to `backend/pyproject.toml`**

Edit the `dependencies` and `dev` lists:

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "sphinx>=7.4",
    "httpx2>=2.9",
    "testcontainers>=4.8",
]
```

Then: `cd backend && pip install -e ".[dev]"`

- [ ] **Step 2: Write the failing test**

`backend/tests/integration/test_event_model.py`:

```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd backend && pytest tests/integration/test_event_model.py -v`
Expected: FAIL (collection error — `app.models` doesn't exist yet, no `db_session` fixture)

- [ ] **Step 4: Create the base mixins**

`backend/app/models/base.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 5: Create the `Event` model**

`backend/app/models/event.py`:

```python
from datetime import date

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Event(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "events"

    date: Mapped[date] = mapped_column(nullable=False)
```

`backend/app/models/__init__.py`:

```python
from app.models.base import Base
from app.models.event import Event

__all__ = ["Base", "Event"]
```

- [ ] **Step 6: Set up Alembic**

`backend/alembic.ini`:

```ini
[alembic]
script_location = alembic
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

`backend/alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`backend/alembic/env.py`:

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`backend/alembic/versions/0001_create_event.py`:

```python
"""create event table

Revision ID: 0001
Revises:
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("events")
```

- [ ] **Step 7: Create the testcontainers fixtures**

`backend/tests/integration/conftest.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def migrated_engine(postgres_url):
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": postgres_url},
        check=True,
    )
    return create_engine(postgres_url)


@pytest.fixture()
def db_session(migrated_engine):
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd backend && pytest tests/integration/test_event_model.py -v`
Expected: PASS (this spins up a real Postgres 16 container via Docker — first run pulls the image and takes longer)

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/app/models/__init__.py backend/app/models/base.py \
  backend/app/models/event.py backend/alembic.ini backend/alembic/env.py \
  backend/alembic/script.py.mako backend/alembic/versions/0001_create_event.py \
  backend/tests/integration/conftest.py backend/tests/integration/test_event_model.py
git commit -m "$(cat <<'EOF'
feat(domain): add Event model, Alembic setup, and testcontainers fixtures

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `Pod` model

**Files:**
- Create: `backend/app/models/pod.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0002_create_pod.py`
- Test: `backend/tests/integration/test_pod_model.py`

**Interfaces:**
- Produces: `app.models.Pod` (columns: `id`, `event_id: Mapped[uuid.UUID]` FK → `events.id`, `format_slug: Mapped[str]`, `game_slug: Mapped[str]`, `created_at`).
- Consumes: `app.models.base.Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin` (Task 1), `app.models.Event` (Task 1), `db_session` fixture (Task 1).

- [ ] **Step 1: Write the failing tests**

`backend/tests/integration/test_pod_model.py`:

```python
import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Event, Pod


def test_pod_persists_linked_to_event(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()

    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    assert pod.id is not None
    assert pod.event_id == event.id


def test_pod_requires_existing_event(db_session):
    pod = Pod(event_id=uuid.uuid4(), format_slug="swiss", game_slug="generic")
    db_session.add(pod)

    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_pod_model.py -v`
Expected: FAIL (`ImportError: cannot import name 'Pod'`)

- [ ] **Step 3: Create the `Pod` model**

`backend/app/models/pod.py`:

```python
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Pod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pods"

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    format_slug: Mapped[str] = mapped_column(nullable=False)
    game_slug: Mapped[str] = mapped_column(nullable=False)
```

Update `backend/app/models/__init__.py`:

```python
from app.models.base import Base
from app.models.event import Event
from app.models.pod import Pod

__all__ = ["Base", "Event", "Pod"]
```

- [ ] **Step 4: Write the migration**

`backend/alembic/versions/0002_create_pod.py`:

```python
"""create pod table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id"),
            nullable=False,
        ),
        sa.Column("format_slug", sa.String(), nullable=False),
        sa.Column("game_slug", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_pods_event_id", "pods", ["event_id"])


def downgrade() -> None:
    op.drop_table("pods")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_pod_model.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/pod.py backend/app/models/__init__.py \
  backend/alembic/versions/0002_create_pod.py backend/tests/integration/test_pod_model.py
git commit -m "$(cat <<'EOF'
feat(domain): add Pod model

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `Entry` model

**Files:**
- Create: `backend/app/models/entry.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0003_create_entry.py`
- Test: `backend/tests/integration/test_entry_model.py`

**Interfaces:**
- Produces: `app.models.Entry` (columns: `id`, `pod_id: Mapped[uuid.UUID]` FK → `pods.id`, `player_uuid: Mapped[uuid.UUID]`, `source_system: Mapped[str]`, `metadata_: Mapped[dict]` mapped to DB column `metadata`, `created_at`; unique constraint on `(pod_id, player_uuid, source_system)`).
- Consumes: `Base`, mixins (Task 1), `app.models.Pod` (Task 2), `db_session` fixture (Task 1).

- [ ] **Step 1: Write the failing tests**

`backend/tests/integration/test_entry_model.py`:

```python
import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Entry, Event, Pod


def _make_pod(db_session) -> Pod:
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    return pod


def test_entry_persists_with_metadata(db_session):
    pod = _make_pod(db_session)
    player_uuid = uuid.uuid4()

    entry = Entry(
        pod_id=pod.id,
        player_uuid=player_uuid,
        source_system="club-checkin",
        metadata_={"display_name": "Ash"},
    )
    db_session.add(entry)
    db_session.commit()

    assert entry.id is not None
    assert entry.metadata_ == {"display_name": "Ash"}


def test_entry_rejects_duplicate_player_in_same_pod(db_session):
    pod = _make_pod(db_session)
    player_uuid = uuid.uuid4()
    db_session.add(
        Entry(pod_id=pod.id, player_uuid=player_uuid, source_system="club-checkin", metadata_={})
    )
    db_session.commit()

    db_session.add(
        Entry(pod_id=pod.id, player_uuid=player_uuid, source_system="club-checkin", metadata_={})
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_entry_model.py -v`
Expected: FAIL (`ImportError: cannot import name 'Entry'`)

- [ ] **Step 3: Create the `Entry` model**

`backend/app/models/entry.py`:

```python
import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Entry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint(
            "pod_id", "player_uuid", "source_system", name="uq_entry_player_per_pod"
        ),
    )

    pod_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pods.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
```

`metadata_` (not `metadata`) because `metadata` is reserved on every SQLAlchemy declarative class (`Base.metadata`); `mapped_column("metadata", ...)` keeps the actual DB column named `metadata`.

Update `backend/app/models/__init__.py`:

```python
from app.models.base import Base
from app.models.entry import Entry
from app.models.event import Event
from app.models.pod import Pod

__all__ = ["Base", "Entry", "Event", "Pod"]
```

- [ ] **Step 4: Write the migration**

`backend/alembic/versions/0003_create_entry.py`:

```python
"""create entry table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods.id"), nullable=False
        ),
        sa.Column("player_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "pod_id", "player_uuid", "source_system", name="uq_entry_player_per_pod"
        ),
    )
    op.create_index("ix_entries_pod_id", "entries", ["pod_id"])


def downgrade() -> None:
    op.drop_table("entries")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_entry_model.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/entry.py backend/app/models/__init__.py \
  backend/alembic/versions/0003_create_entry.py backend/tests/integration/test_entry_model.py
git commit -m "$(cat <<'EOF'
feat(domain): add Entry model

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `Round` and `Match` models

**Files:**
- Create: `backend/app/models/round.py`
- Create: `backend/app/models/match.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0004_create_round_and_match.py`
- Test: `backend/tests/integration/test_round_match_models.py`

**Interfaces:**
- Produces: `app.models.Round` (columns: `id`, `pod_id` FK → `pods.id`, `number: Mapped[int]`, `created_at`; unique `(pod_id, number)`). `app.models.Match` (columns: `id`, `round_id` FK → `rounds.id`, `entry1_id` FK → `entries.id`, `entry2_id` FK → `entries.id` nullable, `result: Mapped[MatchResult]` default `MatchResult.UNREPORTED`, `reported_by: Mapped[str | None]`, `witnessed_by: Mapped[str | None]`, `confirmed_by: Mapped[list]` default `[]`, `created_at`). `app.models.MatchResult` enum: `UNREPORTED`, `ENTRY1_WIN`, `ENTRY2_WIN`, `TIE`.
- Consumes: `Base`, mixins (Task 1), `app.models.Pod` (Task 2), `app.models.Entry` (Task 3), `db_session` fixture (Task 1).

- [ ] **Step 1: Write the failing tests**

`backend/tests/integration/test_round_match_models.py`:

```python
import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Entry, Event, Match, MatchResult, Pod, Round


def _make_pod_with_two_entries(db_session) -> tuple[Pod, Entry, Entry]:
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    entry1 = Entry(
        pod_id=pod.id, player_uuid=uuid.uuid4(), source_system="club-checkin", metadata_={}
    )
    entry2 = Entry(
        pod_id=pod.id, player_uuid=uuid.uuid4(), source_system="club-checkin", metadata_={}
    )
    db_session.add_all([entry1, entry2])
    db_session.flush()
    return pod, entry1, entry2


def test_match_defaults_to_unreported(db_session):
    pod, entry1, entry2 = _make_pod_with_two_entries(db_session)
    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry1.id, entry2_id=entry2.id)
    db_session.add(match)
    db_session.commit()

    assert match.result == MatchResult.UNREPORTED
    assert match.reported_by is None
    assert match.confirmed_by == []


def test_round_number_unique_per_pod(db_session):
    pod, _entry1, _entry2 = _make_pod_with_two_entries(db_session)
    db_session.add(Round(pod_id=pod.id, number=1))
    db_session.commit()

    db_session.add(Round(pod_id=pod.id, number=1))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_match_requires_existing_round(db_session):
    _pod, entry1, entry2 = _make_pod_with_two_entries(db_session)
    match = Match(round_id=uuid.uuid4(), entry1_id=entry1.id, entry2_id=entry2.id)
    db_session.add(match)

    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_round_match_models.py -v`
Expected: FAIL (`ImportError: cannot import name 'Round'`)

- [ ] **Step 3: Create the `Round` model**

`backend/app/models/round.py`:

```python
import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Round(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rounds"
    __table_args__ = (UniqueConstraint("pod_id", "number", name="uq_round_number_per_pod"),)

    pod_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pods.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
```

- [ ] **Step 4: Create the `Match` model**

`backend/app/models/match.py`:

```python
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MatchResult(enum.Enum):
    UNREPORTED = "unreported"
    ENTRY1_WIN = "entry1_win"
    ENTRY2_WIN = "entry2_win"
    TIE = "tie"


class Match(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "matches"

    round_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rounds.id"), nullable=False
    )
    entry1_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entries.id"), nullable=False
    )
    entry2_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entries.id"), nullable=True
    )
    result: Mapped[MatchResult] = mapped_column(
        Enum(MatchResult, name="match_result"),
        nullable=False,
        default=MatchResult.UNREPORTED,
    )
    reported_by: Mapped[str | None] = mapped_column(String, nullable=True)
    witnessed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmed_by: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
```

Update `backend/app/models/__init__.py`:

```python
from app.models.base import Base
from app.models.entry import Entry
from app.models.event import Event
from app.models.match import Match, MatchResult
from app.models.pod import Pod
from app.models.round import Round

__all__ = ["Base", "Entry", "Event", "Match", "MatchResult", "Pod", "Round"]
```

- [ ] **Step 5: Write the migration**

`backend/alembic/versions/0004_create_round_and_match.py`:

```python
"""create round and match tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

match_result_enum = postgresql.ENUM(
    "unreported", "entry1_win", "entry2_win", "tie", name="match_result"
)


def upgrade() -> None:
    op.create_table(
        "rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods.id"), nullable=False
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("pod_id", "number", name="uq_round_number_per_pod"),
    )
    op.create_index("ix_rounds_pod_id", "rounds", ["pod_id"])

    match_result_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "round_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rounds.id"), nullable=False
        ),
        sa.Column(
            "entry1_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entries.id"),
            nullable=False,
        ),
        sa.Column(
            "entry2_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entries.id"), nullable=True
        ),
        sa.Column("result", match_result_enum, nullable=False, server_default="unreported"),
        sa.Column("reported_by", sa.String(), nullable=True),
        sa.Column("witnessed_by", sa.String(), nullable=True),
        sa.Column("confirmed_by", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_matches_round_id", "matches", ["round_id"])


def downgrade() -> None:
    op.drop_table("matches")
    match_result_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("rounds")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_round_match_models.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/round.py backend/app/models/match.py backend/app/models/__init__.py \
  backend/alembic/versions/0004_create_round_and_match.py \
  backend/tests/integration/test_round_match_models.py
git commit -m "$(cat <<'EOF'
feat(domain): add Round and Match models

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `TournamentFormat` plugin interface

**Files:**
- Create: `backend/app/formats/__init__.py`
- Create: `backend/app/formats/base.py`
- Create: `backend/tests/unit/__init__.py`
- Test: `backend/tests/unit/test_formats.py`

**Interfaces:**
- Produces: `app.formats.base.Pairing` (frozen dataclass: `entry1_id: uuid.UUID`, `entry2_id: uuid.UUID | None`), `app.formats.base.TournamentFormat` (ABC; class attr `slug: str`; abstract method `generate_round(self, entries: Sequence[Entry], previous_rounds: Sequence[Round]) -> list[Pairing]`).
- Consumes: `app.models.Entry`, `app.models.Round` (Tasks 3–4), for type hints only — no DB access, no import of anything under `app.games` (NFR5 decoupling).

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/__init__.py`: (empty file)

`backend/tests/unit/test_formats.py`:

```python
import uuid

import pytest

from app.formats.base import Pairing, TournamentFormat


def test_tournament_format_is_abstract():
    with pytest.raises(TypeError):
        TournamentFormat()


def test_concrete_format_implements_generate_round():
    class StubFormat(TournamentFormat):
        slug = "stub"

        def generate_round(self, entries, previous_rounds):
            return [Pairing(entry1_id=uuid.uuid4(), entry2_id=None)]

    pairings = StubFormat().generate_round(entries=[], previous_rounds=[])

    assert len(pairings) == 1
    assert pairings[0].entry2_id is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/unit/test_formats.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.formats'`)

- [ ] **Step 3: Write the implementation**

`backend/app/formats/__init__.py`: (empty file)

`backend/app/formats/base.py`:

```python
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from app.models import Entry, Round


@dataclass(frozen=True)
class Pairing:
    entry1_id: uuid.UUID
    entry2_id: uuid.UUID | None  # None means a bye


class TournamentFormat(ABC):
    slug: str

    @abstractmethod
    def generate_round(
        self, entries: Sequence[Entry], previous_rounds: Sequence[Round]
    ) -> list[Pairing]:
        """Return this pod's next round's pairings given its entries and completed prior rounds."""
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/unit/test_formats.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/formats/__init__.py backend/app/formats/base.py \
  backend/tests/unit/__init__.py backend/tests/unit/test_formats.py
git commit -m "$(cat <<'EOF'
feat(domain): add TournamentFormat plugin interface

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `GameModule` plugin interface + generic fallback

**Files:**
- Create: `backend/app/games/__init__.py`
- Create: `backend/app/games/base.py`
- Create: `backend/app/games/generic.py`
- Test: `backend/tests/unit/test_games.py`

**Interfaces:**
- Produces: `app.games.base.GameModule` (ABC; class attr `slug: str`; abstract method `validate_entry_metadata(self, metadata: dict) -> None`, raises `ValueError` on invalid metadata). `app.games.generic.GenericGameModule` (`slug = "generic"`, no-op `validate_entry_metadata`).
- Consumes: nothing from `app.formats` or `app.models` (NFR5 decoupling — no DB, no format awareness).

- [ ] **Step 1: Write the failing test**

`backend/tests/unit/test_games.py`:

```python
import pytest

from app.games.base import GameModule
from app.games.generic import GenericGameModule


def test_game_module_is_abstract():
    with pytest.raises(TypeError):
        GameModule()


def test_generic_game_module_accepts_any_metadata():
    module = GenericGameModule()

    module.validate_entry_metadata({"anything": "goes"})
    module.validate_entry_metadata({})

    assert module.slug == "generic"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/unit/test_games.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.games'`)

- [ ] **Step 3: Write the implementation**

`backend/app/games/__init__.py`: (empty file)

`backend/app/games/base.py`:

```python
from abc import ABC, abstractmethod


class GameModule(ABC):
    slug: str

    @abstractmethod
    def validate_entry_metadata(self, metadata: dict) -> None:
        """Raise ValueError if metadata is invalid for this game."""
```

`backend/app/games/generic.py`:

```python
from app.games.base import GameModule


class GenericGameModule(GameModule):
    slug = "generic"

    def validate_entry_metadata(self, metadata: dict) -> None:
        return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/unit/test_games.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/games/__init__.py backend/app/games/base.py backend/app/games/generic.py \
  backend/tests/unit/test_games.py
git commit -m "$(cat <<'EOF'
feat(domain): add GameModule plugin interface and generic fallback

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Verify migrations on real `opentourney-staging` Postgres

No code changes — this is the issue #3 acceptance criterion "Alembic migrations for all models, verified applied on staging" plus this repo's NFR3 ("every phase verified against real Kubernetes staging environment"). Run by whoever executes the mandatory manual-verification gate before merge.

**Files:** none.

- [ ] **Step 1: Find the staging Postgres connection secret**

The Percona PG Operator (v2) auto-creates a user secret. Confirm its exact name (pattern is `<clusterName>-pguser-<username>`, cluster name is `opentourney-staging-pg` per `charts/opentourney/values.staging.yaml`):

```bash
kubectl get secrets -n opentourney-staging | grep pguser
```

- [ ] **Step 2: Get the connection URI and the primary service name**

```bash
kubectl get secret -n opentourney-staging <secret-name-from-step-1> -o jsonpath='{.data.uri}' | base64 -d
kubectl get svc -n opentourney-staging
```

The `uri` key is a ready-to-use `postgresql://...` connection string. Note the primary/read-write service name from the `svc` list (Percona v2 convention is `<clusterName>-primary`) for the port-forward target.

- [ ] **Step 3: Port-forward to the primary Postgres service**

```bash
kubectl port-forward -n opentourney-staging svc/<primary-service-name> 5433:5432
```

- [ ] **Step 4: Run the migrations against staging, pointed at the forwarded port**

In a second terminal, rewrite the host:port from the `uri` in Step 2 to `localhost:5433` and export it:

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://<user>:<password>@localhost:5433/opentourney"
python -m alembic upgrade head
```

Expected: Alembic reports upgrading `-> 0001, 0002, 0003, 0004` with no errors.

- [ ] **Step 5: Confirm the five tables exist**

```bash
psql "$DATABASE_URL" -c '\dt'
```

Expected: `events`, `pods`, `entries`, `rounds`, `matches` all listed.

- [ ] **Step 6: Tear down the port-forward**

Stop the `kubectl port-forward` process (Ctrl-C). No commit for this task — it's verification only, recorded in the PR description / manual-verification checklist.

---

## Self-Review Notes

- **Spec coverage**: FR7 (Event) → Task 1. FR8 (Pod, many-per-event schema) → Task 2. FR9 (Entry + Round + Match, BO1 + provenance) → Tasks 3–4. FR12 partial (GameModule interface + generic fallback; Swiss/decklist-specific work stays out of scope) → Task 6. FR10's *interface* half (full Swiss implementation is Phase 4) → Task 5. NFR5 (decoupled interfaces) → Tasks 5–6 have no cross-imports. Issue #3's "Alembic migrations ... verified applied on staging" → Task 7.
- **Placeholder scan**: no TBD/TODO markers; every step has runnable code.
- **Type consistency**: `Pairing`, `TournamentFormat.generate_round`, `GameModule.validate_entry_metadata`, `MatchResult`, and all model field names are defined once (Tasks 1–6) and referenced identically in every later task's Interfaces block and test code.
