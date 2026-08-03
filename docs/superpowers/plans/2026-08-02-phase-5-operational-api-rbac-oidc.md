# Phase 5 — Operational API + RBAC + OIDC + OpenAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Phase 3 domain model and Phase 4 `TournamentFormat`/`GameModule` interfaces into real, DB-backed FastAPI endpoints for the first time — CRUD for events/pods/entries, OIDC-validated identity, RBAC scoped per event/pod, a published/versioned OpenAPI spec, and generic `GameModule` validation wired into Entry creation. Closes GitHub issue #5 (FR12 completion, FR13–FR16).

**Architecture:** A new `app/auth` package validates an externally-issued OIDC bearer token (PyJWT + JWKS, real or static) into an `Identity(player_uuid, source_system)`, which two new RBAC tables (`event_organizers`, `pod_roles`) map to per-event/per-pod authorization via FastAPI dependencies. Three new routers (events, pods, entries) plus a pod-role-assignment router expose CRUD gated by those dependencies. A generated-vs-committed OpenAPI diff test keeps `docs/openapi.json` from drifting. This is the first phase where the running app touches the database and a real identity token, so DB session wiring and Helm secret/env plumbing are built here too, not assumed to already exist.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 + Alembic (existing), PyJWT (`pyjwt[crypto]`, new dependency) + `jwt.PyJWKClient`/`PyJWKSet`, Pydantic v2 schemas, testcontainers-python (existing, real Postgres in integration tests).

## Global Constraints

- Python ≥3.12, FastAPI ≥0.115, SQLAlchemy ≥2.0, Pydantic ≥2.7, Alembic ≥1.13 (existing floors, `backend/pyproject.toml`).
- New runtime dependency: `pyjwt[crypto]>=2.9` — the only new dependency this phase adds.
- TDD (RED → GREEN → REFACTOR) for every task; integration tests use a real Postgres via `testcontainers-python` (existing `tests/integration/conftest.py` fixtures: `postgres_url`, `migrated_engine`, `db_session`) — never mocked DB.
- Migration files follow the existing hand-written-revision convention in `backend/alembic/versions/000N_*.py` (sequential zero-padded numbers, `revision`/`down_revision` strings, explicit `upgrade()`/`downgrade()`); next number is `0006`.
- Ruff: line-length 100, target `py312` (`backend/pyproject.toml`); all new code must pass `ruff check app tests`.
- No self-registration endpoint — Entry creation is always Organizer-gated (FR13, README non-goal).
- OpenTourney owns no accounts/passwords (NFR4) — the auth layer only ever *validates* an externally-issued assertion, never issues or stores credentials.
- `TournamentFormat` and `GameModule` stay fully decoupled (NFR5) — the entries router calls `app.games.registry`, never anything under `app.formats`.
- Never push directly to `main`; never merge without explicit in-the-moment approval.
- This phase is split into **4 sequenced PRs** (see `DECISIONS.md`, 2026-08-02 "Phase 5 split into 4 sequenced PRs"), each its own branch off `main`, each independently reviewable/testable. Issue #5 stays open until PR4 merges.

---

## PR 1 — DB session, OIDC/JWT validation, RBAC tables

**Branch:** `feat/phase-5-operational-api-rbac-oidc` (already created). No HTTP routes are added in this PR — it's pure plumbing, exercised through direct unit/integration tests and one throwaway test-only FastAPI app for the dependency tests.

### Task 1: Settings + DB session dependency

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Modify: `backend/alembic/env.py:16-24` (reuse the new `normalize_database_url` instead of its inline duplicate)
- Test: `backend/tests/integration/test_db_session.py`
- Test: `backend/tests/unit/test_config.py`

**Interfaces:**
- Produces: `app.config.Settings` (frozen dataclass: `database_url: str`, `oidc_issuer: str`, `oidc_audience: str`, `oidc_jwks_url: str | None`, `oidc_jwks_static: str | None`); `app.config.get_settings() -> Settings` (env-var-backed, `functools.lru_cache`d); `app.config.normalize_database_url(raw_url: str) -> str`.
- Produces: `app.db.get_engine()` (`lru_cache`d), `app.db.get_db_session() -> Iterator[Session]` (FastAPI dependency).
- Consumes: nothing from other tasks (this is the foundation task).

- [ ] **Step 1: Write the failing unit test for URL normalization**

```python
# backend/tests/unit/test_config.py
from app.config import normalize_database_url


def test_normalizes_bare_postgresql_scheme():
    assert (
        normalize_database_url("postgresql://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )


def test_normalizes_bare_postgres_scheme():
    assert (
        normalize_database_url("postgres://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )


def test_leaves_already_qualified_scheme_untouched():
    assert (
        normalize_database_url("postgresql+psycopg://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Write `app/config.py`**

```python
# backend/app/config.py
import os
from dataclasses import dataclass
from functools import lru_cache


def normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
    return raw_url


@dataclass(frozen=True)
class Settings:
    database_url: str
    oidc_issuer: str
    oidc_audience: str
    oidc_jwks_url: str | None
    oidc_jwks_static: str | None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=normalize_database_url(os.environ["DATABASE_URL"]),
        oidc_issuer=os.environ["OIDC_ISSUER"],
        oidc_audience=os.environ["OIDC_AUDIENCE"],
        oidc_jwks_url=os.environ.get("OIDC_JWKS_URL"),
        oidc_jwks_static=os.environ.get("OIDC_JWKS_STATIC"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing integration test for the DB session dependency**

```python
# backend/tests/integration/test_db_session.py
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
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_db_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 7: Write `app/db.py`**

```python
# backend/app/db.py
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
```

- [ ] **Step 8: Refactor `alembic/env.py` to reuse `normalize_database_url`**

Replace the inline scheme-normalization block in `backend/alembic/env.py` (currently lines ~16-24) with:

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import normalize_database_url
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ConfigParser.set() performs %-style interpolation, so a raw "%" in the URL
# (e.g. a percent-encoded password from the Percona secret) raises
# InterpolationSyntaxError unless it's escaped as "%%" first.
database_url = normalize_database_url(os.environ["DATABASE_URL"].replace("%", "%%"))

config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata
```

(Keep the rest of `env.py` — `run_migrations_offline`/`run_migrations_online` and the dispatch at the bottom — unchanged.)

- [ ] **Step 9: Run full test suite to verify no regression**

Run: `cd backend && pytest -v`
Expected: PASS — all existing tests plus the two new ones (the `migrated_engine` fixture running `alembic upgrade head` via subprocess is the regression check for the `env.py` refactor)

- [ ] **Step 10: Commit**

```bash
cd backend
git add app/config.py app/db.py alembic/env.py tests/unit/test_config.py tests/integration/test_db_session.py
git commit -m "feat: add Settings and DB session dependency"
```

---

### Task 2: RBAC tables — `EventOrganizer` and `PodRole`

**Files:**
- Create: `backend/app/models/rbac.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0006_create_rbac_tables.py`
- Test: `backend/tests/integration/test_rbac_models.py`

**Interfaces:**
- Produces: `app.models.rbac.PodRoleName` (`str, enum.Enum`: `SCOREKEEPER = "scorekeeper"`, `USER = "user"`); `app.models.rbac.EventOrganizer` (columns: `id`, `event_id`, `player_uuid`, `source_system`, `created_at`; unique on `(event_id, player_uuid, source_system)`); `app.models.rbac.PodRole` (columns: `id`, `pod_id`, `player_uuid`, `source_system`, `role`, `created_at`; unique on `(pod_id, player_uuid, source_system)`).
- Consumes: `app.models.base.Base`, `TimestampMixin`, `UUIDPrimaryKeyMixin` (existing, Phase 3).

- [ ] **Step 1: Write the failing integration tests**

```python
# backend/tests/integration/test_rbac_models.py
import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Event, Pod
from app.models.rbac import EventOrganizer, PodRole, PodRoleName


def _make_event(db_session) -> Event:
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    return event


def _make_pod(db_session, event) -> Pod:
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    return pod


def test_event_organizer_persists(db_session):
    event = _make_event(db_session)
    player_uuid = uuid.uuid4()

    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()

    row = db_session.query(EventOrganizer).one()
    assert row.event_id == event.id
    assert row.player_uuid == player_uuid


def test_event_organizer_rejects_duplicate_identity_per_event(db_session):
    event = _make_event(db_session)
    player_uuid = uuid.uuid4()
    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()

    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_event_organizer_requires_existing_event(db_session):
    db_session.add(
        EventOrganizer(event_id=uuid.uuid4(), player_uuid=uuid.uuid4(), source_system="x")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_pod_role_persists_with_role_enum(db_session):
    event = _make_event(db_session)
    pod = _make_pod(db_session, event)
    player_uuid = uuid.uuid4()

    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.SCOREKEEPER,
        )
    )
    db_session.commit()

    row = db_session.query(PodRole).one()
    assert row.role == PodRoleName.SCOREKEEPER


def test_pod_role_rejects_duplicate_identity_per_pod(db_session):
    event = _make_event(db_session)
    pod = _make_pod(db_session, event)
    player_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.USER,
        )
    )
    db_session.commit()

    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.SCOREKEEPER,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_rbac_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.rbac'`

- [ ] **Step 3: Write `app/models/rbac.py`**

```python
# backend/app/models/rbac.py
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PodRoleName(str, enum.Enum):
    SCOREKEEPER = "scorekeeper"
    USER = "user"


class EventOrganizer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "event_organizers"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "player_uuid", "source_system", name="uq_event_organizer_identity"
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)


class PodRole(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pod_roles"
    __table_args__ = (
        UniqueConstraint("pod_id", "player_uuid", "source_system", name="uq_pod_role_identity"),
    )

    pod_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pods.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[PodRoleName] = mapped_column(
        Enum(
            PodRoleName,
            name="pod_role_name",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
```

- [ ] **Step 4: Update `app/models/__init__.py`**

```python
# backend/app/models/__init__.py
from app.models.base import Base
from app.models.entry import Entry
from app.models.event import Event
from app.models.match import Match, MatchResult
from app.models.pod import Pod
from app.models.rbac import EventOrganizer, PodRole, PodRoleName
from app.models.round import Round

__all__ = [
    "Base",
    "Entry",
    "Event",
    "EventOrganizer",
    "Match",
    "MatchResult",
    "Pod",
    "PodRole",
    "PodRoleName",
    "Round",
]
```

- [ ] **Step 5: Write migration `0006_create_rbac_tables.py`**

```python
# backend/alembic/versions/0006_create_rbac_tables.py
"""create rbac tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# create_type=False keeps op.create_table() from re-emitting its own CREATE TYPE for this
# enum; the type is created explicitly below via pod_role_name_enum.create(), matching the
# pattern in 0004_create_round_and_match.py.
pod_role_name_enum = postgresql.ENUM(
    "scorekeeper",
    "user",
    name="pod_role_name",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "event_organizers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False
        ),
        sa.Column("player_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "event_id", "player_uuid", "source_system", name="uq_event_organizer_identity"
        ),
    )
    op.create_index("ix_event_organizers_event_id", "event_organizers", ["event_id"])

    pod_role_name_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "pod_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods.id"), nullable=False
        ),
        sa.Column("player_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("role", pod_role_name_enum, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "pod_id", "player_uuid", "source_system", name="uq_pod_role_identity"
        ),
    )
    op.create_index("ix_pod_roles_pod_id", "pod_roles", ["pod_id"])


def downgrade() -> None:
    op.drop_table("pod_roles")
    pod_role_name_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("event_organizers")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_rbac_models.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/models/rbac.py app/models/__init__.py alembic/versions/0006_create_rbac_tables.py tests/integration/test_rbac_models.py
git commit -m "feat: add EventOrganizer and PodRole RBAC tables"
```

---

### Task 3: Shared test-JWT keypair/minting helper

**Files:**
- Create: `backend/tests/support/__init__.py`
- Create: `backend/tests/support/jwt_helpers.py`
- Test: `backend/tests/unit/test_jwt_helpers.py`

**Interfaces:**
- Produces: `tests.support.jwt_helpers.generate_test_keypair(kid: str = "test-key") -> tuple[RSAPrivateKey, str]` (private key object, JSON string of a JWK set containing the matching public key); `tests.support.jwt_helpers.mint_token(private_key, *, kid: str, issuer: str, audience: str, player_uuid, source_system: str, roles: list[str] | None = None, expires_in: int = 3600) -> str`.
- Consumes: `pyjwt[crypto]` (added to `backend/pyproject.toml` dev dependencies is not needed — it's a main dependency, see Task 5).

- [ ] **Step 1: Write the failing unit test**

```python
# backend/tests/unit/test_jwt_helpers.py
import json
import uuid

import jwt

from tests.support.jwt_helpers import generate_test_keypair, mint_token


def test_generate_test_keypair_returns_usable_jwk_set():
    _, jwks_json = generate_test_keypair(kid="k1")

    jwk_set = json.loads(jwks_json)

    assert jwk_set["keys"][0]["kid"] == "k1"
    assert jwk_set["keys"][0]["kty"] == "RSA"


def test_mint_token_is_decodable_with_the_matching_public_key():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    player_uuid = uuid.uuid4()

    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="opentourney-test",
        player_uuid=player_uuid,
        source_system="club-checkin",
        roles=["organizer"],
    )

    signing_key = jwt.PyJWKSet.from_json(jwks_json).keys[0]
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience="opentourney-test",
        issuer="https://issuer.example.com",
    )

    assert claims["sub"] == str(player_uuid)
    assert claims["source_system"] == "club-checkin"
    assert claims["roles"] == ["organizer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_jwt_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.support'`

- [ ] **Step 3: Add the `pyjwt[crypto]` dependency**

In `backend/pyproject.toml`, add to the `[project]` `dependencies` list (alongside the existing `fastapi`, `sqlalchemy`, etc.):

```toml
    "pyjwt[crypto]>=2.9",
```

Then reinstall:

Run: `cd backend && pip install -e ".[dev]"`

- [ ] **Step 4: Write `tests/support/jwt_helpers.py`**

```python
# backend/tests/support/__init__.py
```

```python
# backend/tests/support/jwt_helpers.py
import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


def generate_test_keypair(kid: str = "test-key"):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk["kid"] = kid
    public_jwk["use"] = "sig"
    public_jwk["alg"] = "RS256"
    jwks_json = json.dumps({"keys": [public_jwk]})
    return private_key, jwks_json


def mint_token(
    private_key,
    *,
    kid: str,
    issuer: str,
    audience: str,
    player_uuid: uuid.UUID | str,
    source_system: str,
    roles: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": str(player_uuid),
        "source_system": source_system,
        "roles": roles or [],
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_jwt_helpers.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
cd backend
git add pyproject.toml tests/support/__init__.py tests/support/jwt_helpers.py tests/unit/test_jwt_helpers.py
git commit -m "test: add shared RSA keypair/JWT-minting helper for auth tests"
```

---

### Task 4: JWKS key providers (remote + static)

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/jwks.py`
- Test: `backend/tests/unit/test_jwks.py`

**Interfaces:**
- Produces: `app.auth.jwks.JWKSProvider` (Protocol: `get_signing_key(token: str) -> jwt.PyJWK`); `app.auth.jwks.RemoteJWKSProvider(jwks_url: str)`; `app.auth.jwks.StaticJWKSProvider(jwks_json: str)`; `app.auth.jwks.build_jwks_provider(settings: Settings) -> JWKSProvider`.
- Consumes: `app.config.Settings` (Task 1); `tests.support.jwt_helpers.generate_test_keypair`, `mint_token` (Task 3).

- [ ] **Step 1: Write the failing unit tests**

```python
# backend/tests/unit/test_jwks.py
import pytest

from app.auth.jwks import StaticJWKSProvider, build_jwks_provider
from app.config import Settings
from tests.support.jwt_helpers import generate_test_keypair, mint_token


def test_static_provider_returns_matching_key_by_kid():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="aud",
        player_uuid="00000000-0000-0000-0000-000000000000",
        source_system="club-checkin",
    )

    provider = StaticJWKSProvider(jwks_json)
    signing_key = provider.get_signing_key(token)

    assert signing_key.key_id == "k1"


def test_static_provider_raises_for_unknown_kid():
    _, jwks_json = generate_test_keypair(kid="k1")
    other_private_key, _ = generate_test_keypair(kid="k2")
    token = mint_token(
        other_private_key,
        kid="k2",
        issuer="https://issuer.example.com",
        audience="aud",
        player_uuid="00000000-0000-0000-0000-000000000000",
        source_system="club-checkin",
    )

    provider = StaticJWKSProvider(jwks_json)

    with pytest.raises(Exception, match="no JWKS key found"):
        provider.get_signing_key(token)


def test_build_jwks_provider_prefers_static_over_remote():
    _, jwks_json = generate_test_keypair()
    settings = Settings(
        database_url="unused",
        oidc_issuer="https://issuer.example.com",
        oidc_audience="aud",
        oidc_jwks_url="https://issuer.example.com/.well-known/jwks.json",
        oidc_jwks_static=jwks_json,
    )

    provider = build_jwks_provider(settings)

    assert provider.__class__.__name__ == "StaticJWKSProvider"


def test_build_jwks_provider_raises_when_nothing_configured():
    settings = Settings(
        database_url="unused",
        oidc_issuer="https://issuer.example.com",
        oidc_audience="aud",
        oidc_jwks_url=None,
        oidc_jwks_static=None,
    )

    with pytest.raises(RuntimeError, match="neither OIDC_JWKS_STATIC nor OIDC_JWKS_URL"):
        build_jwks_provider(settings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_jwks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Write `app/auth/__init__.py` and `app/auth/jwks.py`**

```python
# backend/app/auth/__init__.py
```

```python
# backend/app/auth/jwks.py
from typing import Protocol

import jwt
from jwt import PyJWK, PyJWKClient, PyJWKSet

from app.config import Settings


class JWKSProvider(Protocol):
    def get_signing_key(self, token: str) -> PyJWK: ...


class RemoteJWKSProvider:
    def __init__(self, jwks_url: str) -> None:
        self._client = PyJWKClient(jwks_url)

    def get_signing_key(self, token: str) -> PyJWK:
        return self._client.get_signing_key_from_jwt(token)


class StaticJWKSProvider:
    def __init__(self, jwks_json: str) -> None:
        self._jwk_set = PyJWKSet.from_json(jwks_json)

    def get_signing_key(self, token: str) -> PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        for key in self._jwk_set.keys:
            if key.key_id == kid:
                return key
        raise jwt.InvalidTokenError(f"no JWKS key found for kid={kid!r}")


def build_jwks_provider(settings: Settings) -> JWKSProvider:
    if settings.oidc_jwks_static:
        return StaticJWKSProvider(settings.oidc_jwks_static)
    if settings.oidc_jwks_url:
        return RemoteJWKSProvider(settings.oidc_jwks_url)
    raise RuntimeError("neither OIDC_JWKS_STATIC nor OIDC_JWKS_URL is configured")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_jwks.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/auth/__init__.py app/auth/jwks.py tests/unit/test_jwks.py
git commit -m "feat: add remote and static JWKS providers"
```

---

### Task 5: Token decoding + identity extraction

**Files:**
- Create: `backend/app/auth/oidc.py`
- Create: `backend/app/auth/identity.py`
- Test: `backend/tests/unit/test_oidc.py`
- Test: `backend/tests/unit/test_identity.py`

**Interfaces:**
- Produces: `app.auth.oidc.AuthError(Exception)`; `app.auth.oidc.decode_token(token: str, settings: Settings, jwks_provider: JWKSProvider) -> dict`; `app.auth.identity.Identity` (frozen dataclass: `player_uuid: uuid.UUID`, `source_system: str`, `has_organizer_claim: bool`); `app.auth.identity.identity_from_claims(claims: dict) -> Identity`.
- Consumes: `app.auth.jwks.JWKSProvider`, `StaticJWKSProvider` (Task 4); `app.config.Settings` (Task 1); `tests.support.jwt_helpers` (Task 3).

- [ ] **Step 1: Write the failing test for `decode_token`**

```python
# backend/tests/unit/test_oidc.py
import pytest

from app.auth.jwks import StaticJWKSProvider
from app.auth.oidc import AuthError, decode_token
from app.config import Settings
from tests.support.jwt_helpers import generate_test_keypair, mint_token


def _settings(jwks_json: str) -> Settings:
    return Settings(
        database_url="unused",
        oidc_issuer="https://issuer.example.com",
        oidc_audience="opentourney-test",
        oidc_jwks_url=None,
        oidc_jwks_static=jwks_json,
    )


def test_decode_token_returns_claims_for_a_valid_token():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="opentourney-test",
        player_uuid="11111111-1111-1111-1111-111111111111",
        source_system="club-checkin",
    )
    settings = _settings(jwks_json)

    claims = decode_token(token, settings, StaticJWKSProvider(jwks_json))

    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"


def test_decode_token_rejects_wrong_audience():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="someone-else",
        player_uuid="11111111-1111-1111-1111-111111111111",
        source_system="club-checkin",
    )
    settings = _settings(jwks_json)

    with pytest.raises(AuthError):
        decode_token(token, settings, StaticJWKSProvider(jwks_json))


def test_decode_token_rejects_tampered_signature():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="opentourney-test",
        player_uuid="11111111-1111-1111-1111-111111111111",
        source_system="club-checkin",
    )
    settings = _settings(jwks_json)

    with pytest.raises(AuthError):
        decode_token(token + "x", settings, StaticJWKSProvider(jwks_json))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_oidc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.oidc'`

- [ ] **Step 3: Write `app/auth/oidc.py`**

```python
# backend/app/auth/oidc.py
import jwt

from app.auth.jwks import JWKSProvider
from app.config import Settings


class AuthError(Exception):
    """Raised when an identity assertion fails to validate."""


def decode_token(token: str, settings: Settings, jwks_provider: JWKSProvider) -> dict:
    try:
        signing_key = jwks_provider.get_signing_key(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_oidc.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing test for `identity_from_claims`**

```python
# backend/tests/unit/test_identity.py
import uuid

import pytest

from app.auth.identity import identity_from_claims
from app.auth.oidc import AuthError


def test_identity_from_claims_extracts_player_and_source_system():
    player_uuid = uuid.uuid4()

    identity = identity_from_claims(
        {"sub": str(player_uuid), "source_system": "club-checkin", "roles": []}
    )

    assert identity.player_uuid == player_uuid
    assert identity.source_system == "club-checkin"
    assert identity.has_organizer_claim is False


def test_identity_from_claims_detects_organizer_role():
    identity = identity_from_claims(
        {
            "sub": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "roles": ["organizer"],
        }
    )

    assert identity.has_organizer_claim is True


def test_identity_from_claims_raises_for_missing_sub():
    with pytest.raises(AuthError):
        identity_from_claims({"source_system": "club-checkin"})


def test_identity_from_claims_raises_for_missing_source_system():
    with pytest.raises(AuthError):
        identity_from_claims({"sub": str(uuid.uuid4())})
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.identity'`

- [ ] **Step 7: Write `app/auth/identity.py`**

```python
# backend/app/auth/identity.py
import uuid
from dataclasses import dataclass

from app.auth.oidc import AuthError


@dataclass(frozen=True)
class Identity:
    player_uuid: uuid.UUID
    source_system: str
    has_organizer_claim: bool


def identity_from_claims(claims: dict) -> Identity:
    try:
        player_uuid = uuid.UUID(str(claims["sub"]))
        source_system = claims["source_system"]
    except (KeyError, ValueError) as exc:
        raise AuthError(
            "token is missing required identity claims (sub, source_system)"
        ) from exc

    roles = claims.get("roles", [])
    return Identity(
        player_uuid=player_uuid,
        source_system=source_system,
        has_organizer_claim="organizer" in roles,
    )
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_identity.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Commit**

```bash
cd backend
git add app/auth/oidc.py app/auth/identity.py tests/unit/test_oidc.py tests/unit/test_identity.py
git commit -m "feat: add OIDC token decoding and identity extraction"
```

---

### Task 6: FastAPI auth/RBAC dependencies

**Files:**
- Create: `backend/app/auth/dependencies.py`
- Modify: `backend/tests/integration/conftest.py` (add `test_keypair`, `test_settings`, `make_token` fixtures)
- Test: `backend/tests/integration/test_auth_dependencies.py`

**Interfaces:**
- Produces: `app.auth.dependencies.get_jwks_provider`, `get_current_identity`, `require_organizer_claim`, `require_event_organizer`, `require_pod_organizer`, `require_pod_access` (all FastAPI dependencies returning `Identity` or raising `HTTPException`); `app.auth.dependencies.event_organizer_exists(db, identity, event_id) -> bool`; `pod_role_exists(db, identity, pod_id) -> bool`; `visible_event_ids(db, identity) -> set[uuid.UUID]` (plain helper functions, reused directly by routers for body-scoped checks in later PRs).
- Consumes: `app.auth.identity.Identity`, `identity_from_claims` (Task 5); `app.auth.oidc.AuthError`, `decode_token` (Task 5); `app.auth.jwks.JWKSProvider`, `build_jwks_provider` (Task 4); `app.config.Settings`, `get_settings` (Task 1); `app.db.get_db_session` (Task 1); `app.models.rbac.EventOrganizer`, `PodRole` (Task 2); `app.models.pod.Pod` (Phase 3); `tests.support.jwt_helpers` (Task 3).

- [ ] **Step 1: Add shared auth-test fixtures to `tests/integration/conftest.py`**

Append to the existing `backend/tests/integration/conftest.py` (after the `db_session` fixture):

```python
from app.config import Settings
from tests.support.jwt_helpers import generate_test_keypair, mint_token


@pytest.fixture()
def test_keypair():
    return generate_test_keypair()


@pytest.fixture()
def test_settings(test_keypair):
    _, jwks_json = test_keypair
    return Settings(
        database_url="unused-in-tests",
        oidc_issuer="https://test-issuer.example.com",
        oidc_audience="opentourney-test",
        oidc_jwks_url=None,
        oidc_jwks_static=jwks_json,
    )


@pytest.fixture()
def make_token(test_keypair, test_settings):
    private_key, _ = test_keypair

    def _make(*, player_uuid, source_system="club-checkin", roles=None):
        return mint_token(
            private_key,
            kid="test-key",
            issuer=test_settings.oidc_issuer,
            audience=test_settings.oidc_audience,
            player_uuid=player_uuid,
            source_system=source_system,
            roles=roles,
        )

    return _make
```

- [ ] **Step 2: Write the failing integration tests**

```python
# backend/tests/integration/test_auth_dependencies.py
import uuid
from datetime import date

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_identity, require_event_organizer, require_pod_access
from app.auth.identity import Identity
from app.config import get_settings
from app.db import get_db_session
from app.models import Event, Pod
from app.models.rbac import EventOrganizer, PodRole


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(identity: Identity = Depends(get_current_identity)) -> dict:
        return {"player_uuid": str(identity.player_uuid), "source_system": identity.source_system}

    @app.get("/events/{event_id}/organizer-only")
    def organizer_only(
        event_id: uuid.UUID, identity: Identity = Depends(require_event_organizer)
    ) -> dict:
        return {"ok": True}

    @app.get("/pods/{pod_id}/access-only")
    def access_only(pod_id: uuid.UUID, identity: Identity = Depends(require_pod_access)) -> dict:
        return {"ok": True}

    return app


def _client(app: FastAPI, db_session, settings) -> TestClient:
    def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_valid_token_resolves_identity(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    player_uuid = uuid.uuid4()
    token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "player_uuid": str(player_uuid),
        "source_system": "club-checkin",
    }


def test_missing_token_is_rejected(db_session, test_settings):
    client = _client(_build_test_app(), db_session, test_settings)

    response = client.get("/whoami")

    assert response.status_code == 403  # HTTPBearer's own missing-credentials response


def test_tampered_token_is_rejected(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4())

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}x"})

    assert response.status_code == 401


def test_event_organizer_row_grants_access(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = client.get(
        f"/events/{event.id}/organizer-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


def test_no_event_organizer_row_is_forbidden(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), source_system="club-checkin")

    response = client.get(
        f"/events/{event.id}/organizer-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_pod_role_grants_pod_access_without_organizer_row(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        PodRole(pod_id=pod.id, player_uuid=player_uuid, source_system="club-checkin", role="user")
    )
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = client.get(
        f"/pods/{pod.id}/access-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


def test_no_role_at_all_is_forbidden_for_pod_access(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), source_system="club-checkin")

    response = client.get(
        f"/pods/{pod.id}/access-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_auth_dependencies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.dependencies'`

- [ ] **Step 4: Write `app/auth/dependencies.py`**

```python
# backend/app/auth/dependencies.py
import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.identity import Identity, identity_from_claims
from app.auth.jwks import JWKSProvider, build_jwks_provider
from app.auth.oidc import AuthError, decode_token
from app.config import Settings, get_settings
from app.db import get_db_session
from app.models.pod import Pod
from app.models.rbac import EventOrganizer, PodRole

_bearer_scheme = HTTPBearer()


def get_jwks_provider(settings: Settings = Depends(get_settings)) -> JWKSProvider:
    return build_jwks_provider(settings)


def get_current_identity(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
    jwks_provider: JWKSProvider = Depends(get_jwks_provider),
) -> Identity:
    try:
        claims = decode_token(credentials.credentials, settings, jwks_provider)
        return identity_from_claims(claims)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_organizer_claim(identity: Identity = Depends(get_current_identity)) -> Identity:
    if not identity.has_organizer_claim:
        raise HTTPException(status_code=403, detail="organizer claim required")
    return identity


def event_organizer_exists(db: Session, identity: Identity, event_id: uuid.UUID) -> bool:
    return (
        db.query(EventOrganizer)
        .filter_by(
            event_id=event_id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
        )
        .first()
        is not None
    )


def pod_role_exists(db: Session, identity: Identity, pod_id: uuid.UUID) -> bool:
    return (
        db.query(PodRole)
        .filter_by(
            pod_id=pod_id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
        )
        .first()
        is not None
    )


def visible_event_ids(db: Session, identity: Identity) -> set[uuid.UUID]:
    organizer_ids = {
        row.event_id
        for row in db.query(EventOrganizer.event_id).filter_by(
            player_uuid=identity.player_uuid, source_system=identity.source_system
        )
    }
    pod_ids = {
        row.pod_id
        for row in db.query(PodRole.pod_id).filter_by(
            player_uuid=identity.player_uuid, source_system=identity.source_system
        )
    }
    pod_event_ids = (
        {row.event_id for row in db.query(Pod.event_id).filter(Pod.id.in_(pod_ids))}
        if pod_ids
        else set()
    )
    return organizer_ids | pod_event_ids


def require_event_organizer(
    event_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Identity:
    if not event_organizer_exists(db, identity, event_id):
        raise HTTPException(status_code=403, detail="Organizer role required for this event")
    return identity


def require_pod_organizer(
    pod_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Identity:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    if not event_organizer_exists(db, identity, pod.event_id):
        raise HTTPException(
            status_code=403, detail="Organizer role required for this pod's event"
        )
    return identity


def require_pod_access(
    pod_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Identity:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    if not (
        event_organizer_exists(db, identity, pod.event_id)
        or pod_role_exists(db, identity, pod_id)
    ):
        raise HTTPException(status_code=403, detail="no role scoped to this pod")
    return identity
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_auth_dependencies.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the full backend test suite + lint**

Run: `cd backend && pytest -v && ruff check app tests`
Expected: PASS, no lint errors

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/auth/dependencies.py tests/integration/conftest.py tests/integration/test_auth_dependencies.py
git commit -m "feat: add FastAPI auth and RBAC dependencies"
```

**End of PR1.** Open the PR (`gh pr create`), run `/code-review`, then manual verification: since there are no routes yet, verification is "the full test suite (unit + integration against real Postgres) passes and `ruff check` is clean" — confirm and report per-file pass/fail before asking to merge.

---

## PR 2 — Events + Pods CRUD

**Branch:** create fresh off `main` after PR1 merges — `feat/phase-5b-events-pods-crud`.

### Task 7: Event schemas + router

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/event.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/events.py`
- Test: `backend/tests/integration/test_events_api.py`

**Interfaces:**
- Produces: `app.schemas.event.EventCreate(date: date)`, `EventUpdate(date: date)`, `EventRead(id, date)`; `app.routers.events.router` (`APIRouter(prefix="/events")`) with `POST /events`, `GET /events`, `GET /events/{event_id}`, `PATCH /events/{event_id}`, `DELETE /events/{event_id}`.
- Consumes: `app.auth.dependencies.get_current_identity`, `require_event_organizer`, `require_organizer_claim`, `visible_event_ids` (Task 6); `app.db.get_db_session` (Task 1); `app.models.Event`, `Entry`, `Match`, `Pod`, `Round` (Phase 3); `app.models.rbac.EventOrganizer`, `PodRole` (Task 2).

- [ ] **Step 1: Add shared `api_client` fixture to `tests/integration/conftest.py`**

Append to `backend/tests/integration/conftest.py`:

```python
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_db_session
from app.main import app as fastapi_app


@pytest.fixture()
def api_client(db_session, test_settings):
    def override_get_db_session():
        yield db_session

    fastapi_app.dependency_overrides[get_db_session] = override_get_db_session
    fastapi_app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(fastapi_app) as client:
        yield client

    fastapi_app.dependency_overrides.clear()
```

- [ ] **Step 2: Write the failing integration tests**

```python
# backend/tests/integration/test_events_api.py
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_organizer_claim_creates_event_and_becomes_its_organizer(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["date"] == "2026-09-01"

    get_response = api_client.get(f"/events/{body['id']}", headers=_auth_headers(token))
    assert get_response.status_code == 200


def test_non_organizer_claim_cannot_create_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=[])

    response = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    )

    assert response.status_code == 403


def test_unrelated_identity_cannot_read_event(api_client, make_token):
    creator_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    create_response = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(creator_token)
    )
    event_id = create_response.json()["id"]

    other_token = make_token(player_uuid=uuid.uuid4(), roles=[])
    response = api_client.get(f"/events/{event_id}", headers=_auth_headers(other_token))

    assert response.status_code == 403


def test_organizer_can_update_and_delete_own_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_id}", json={"date": "2026-09-02"}, headers=_auth_headers(token)
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["date"] == "2026-09-02"

    delete_response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(token))
    assert get_response.status_code == 404


def test_list_events_only_shows_visible_events(api_client, make_token):
    mine_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    other_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    api_client.post("/events", json={"date": "2026-09-01"}, headers=_auth_headers(mine_token))
    api_client.post("/events", json={"date": "2026-09-05"}, headers=_auth_headers(other_token))

    response = api_client.get("/events", headers=_auth_headers(mine_token))

    assert response.status_code == 200
    dates = [event["date"] for event in response.json()]
    assert dates == ["2026-09-01"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_events_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas'` (or router 404s once `app.main` import succeeds but routes aren't registered)

- [ ] **Step 4: Write `app/schemas/event.py`**

```python
# backend/app/schemas/__init__.py
```

```python
# backend/app/schemas/event.py
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class EventCreate(BaseModel):
    date: dt.date


class EventUpdate(BaseModel):
    date: dt.date


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: dt.date
```

- [ ] **Step 5: Write `app/routers/events.py`**

```python
# backend/app/routers/__init__.py
```

```python
# backend/app/routers/events.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_identity,
    require_event_organizer,
    require_organizer_claim,
    visible_event_ids,
)
from app.auth.identity import Identity
from app.db import get_db_session
from app.models import Entry, Event, Match, Pod, Round
from app.models.rbac import EventOrganizer, PodRole
from app.schemas.event import EventCreate, EventRead, EventUpdate

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventRead, status_code=201)
def create_event(
    payload: EventCreate,
    identity: Identity = Depends(require_organizer_claim),
    db: Session = Depends(get_db_session),
) -> Event:
    event = Event(date=payload.date)
    db.add(event)
    db.flush()
    db.add(
        EventOrganizer(
            event_id=event.id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
        )
    )
    db.commit()
    db.refresh(event)
    return event


@router.get("", response_model=list[EventRead])
def list_events(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Event]:
    ids = visible_event_ids(db, identity)
    if not ids:
        return []
    return db.query(Event).filter(Event.id.in_(ids)).all()


@router.get("/{event_id}", response_model=EventRead)
def get_event(
    event_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    if event_id not in visible_event_ids(db, identity):
        raise HTTPException(status_code=403, detail="no role scoped to this event")
    return event


@router.patch("/{event_id}", response_model=EventRead)
def update_event(
    event_id: uuid.UUID,
    payload: EventUpdate,
    identity: Identity = Depends(require_event_organizer),
    db: Session = Depends(get_db_session),
) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    event.date = payload.date
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: uuid.UUID,
    identity: Identity = Depends(require_event_organizer),
    db: Session = Depends(get_db_session),
) -> None:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")

    for pod in db.query(Pod).filter_by(event_id=event_id).all():
        for round_ in db.query(Round).filter_by(pod_id=pod.id).all():
            db.query(Match).filter_by(round_id=round_.id).delete()
        db.query(Round).filter_by(pod_id=pod.id).delete()
        db.query(Entry).filter_by(pod_id=pod.id).delete()
        db.query(PodRole).filter_by(pod_id=pod.id).delete()
        db.delete(pod)
    db.query(EventOrganizer).filter_by(event_id=event_id).delete()
    db.delete(event)
    db.commit()
```

- [ ] **Step 6: Wire the router into `app/main.py`**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.routers import events

app = FastAPI(title="OpenTourney")
app.include_router(events.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_events_api.py -v`
Expected: PASS (5 tests)

- [ ] **Step 8: Commit**

```bash
cd backend
git add app/schemas app/routers app/main.py tests/integration/conftest.py tests/integration/test_events_api.py
git commit -m "feat: add Events CRUD endpoints"
```

---

### Task 8: Pod schemas + router (one-pod-per-event enforced)

**Files:**
- Create: `backend/app/schemas/pod.py`
- Create: `backend/app/routers/pods.py`
- Test: `backend/tests/integration/test_pods_api.py`

**Interfaces:**
- Produces: `app.schemas.pod.PodCreate(event_id, format_slug, game_slug)`, `PodUpdate(format_slug, game_slug)`, `PodRead(id, event_id, format_slug, game_slug)`; `app.routers.pods.router` (`APIRouter(prefix="/pods")`) with `POST /pods`, `GET /pods?event_id=`, `GET /pods/{pod_id}`, `PATCH /pods/{pod_id}`, `DELETE /pods/{pod_id}`.
- Consumes: `app.auth.dependencies.event_organizer_exists`, `get_current_identity`, `require_pod_access`, `require_pod_organizer`, `visible_event_ids` (Task 6); `app.models.Pod`, `Entry`, `Match`, `Round` (Phase 3); `app.models.rbac.PodRole` (Task 2).

- [ ] **Step 1: Write the failing integration tests**

```python
# backend/tests/integration/test_pods_api.py
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_event(api_client, token) -> str:
    response = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    )
    return response.json()["id"]


def test_organizer_creates_pod_for_own_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)

    response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["event_id"] == event_id


def test_second_pod_for_same_event_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)
    api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )

    response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_non_organizer_cannot_create_pod(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_organizer_can_update_and_delete_pod(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)
    pod_id = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/pods/{pod_id}",
        json={"format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )
    assert patch_response.status_code == 200

    delete_response = api_client.delete(f"/pods/{pod_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    get_response = api_client.get(f"/pods/{pod_id}", headers=_auth_headers(token))
    assert get_response.status_code == 404


def test_list_pods_requires_event_visibility(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, owner_token)
    api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(owner_token),
    )

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=[])
    response = api_client.get(
        "/pods", params={"event_id": event_id}, headers=_auth_headers(stranger_token)
    )

    assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_pods_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.pod'`

- [ ] **Step 3: Write `app/schemas/pod.py`**

```python
# backend/app/schemas/pod.py
import uuid

from pydantic import BaseModel, ConfigDict


class PodCreate(BaseModel):
    event_id: uuid.UUID
    format_slug: str
    game_slug: str


class PodUpdate(BaseModel):
    format_slug: str
    game_slug: str


class PodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    format_slug: str
    game_slug: str
```

- [ ] **Step 4: Write `app/routers/pods.py`**

```python
# backend/app/routers/pods.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    event_organizer_exists,
    get_current_identity,
    require_pod_access,
    require_pod_organizer,
    visible_event_ids,
)
from app.auth.identity import Identity
from app.db import get_db_session
from app.models import Entry, Match, Pod, Round
from app.models.rbac import PodRole
from app.schemas.pod import PodCreate, PodRead, PodUpdate

router = APIRouter(prefix="/pods", tags=["pods"])


@router.post("", response_model=PodRead, status_code=201)
def create_pod(
    payload: PodCreate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Pod:
    if not event_organizer_exists(db, identity, payload.event_id):
        raise HTTPException(status_code=403, detail="Organizer role required for this event")

    existing = db.query(Pod).filter_by(event_id=payload.event_id).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="event already has a pod; v1 supports exactly one pod per event",
        )

    pod = Pod(
        event_id=payload.event_id,
        format_slug=payload.format_slug,
        game_slug=payload.game_slug,
    )
    db.add(pod)
    db.commit()
    db.refresh(pod)
    return pod


@router.get("", response_model=list[PodRead])
def list_pods(
    event_id: uuid.UUID = Query(...),
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Pod]:
    if event_id not in visible_event_ids(db, identity):
        raise HTTPException(status_code=403, detail="no role scoped to this event")
    return db.query(Pod).filter_by(event_id=event_id).all()


@router.get("/{pod_id}", response_model=PodRead)
def get_pod(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> Pod:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    return pod


@router.patch("/{pod_id}", response_model=PodRead)
def update_pod(
    pod_id: uuid.UUID,
    payload: PodUpdate,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> Pod:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    pod.format_slug = payload.format_slug
    pod.game_slug = payload.game_slug
    db.commit()
    db.refresh(pod)
    return pod


@router.delete("/{pod_id}", status_code=204)
def delete_pod(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> None:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")

    for round_ in db.query(Round).filter_by(pod_id=pod_id).all():
        db.query(Match).filter_by(round_id=round_.id).delete()
    db.query(Round).filter_by(pod_id=pod_id).delete()
    db.query(Entry).filter_by(pod_id=pod_id).delete()
    db.query(PodRole).filter_by(pod_id=pod_id).delete()
    db.delete(pod)
    db.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_pods_api.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/schemas/pod.py app/routers/pods.py tests/integration/test_pods_api.py
git commit -m "feat: add Pods CRUD endpoints with one-pod-per-event constraint"
```

---

### Task 9: Wire Pods router into the app

**Files:**
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `app.routers.pods.router` (Task 8).
- Produces: nothing new — this task only registers the router.

- [ ] **Step 1: Run the existing Pods API tests to confirm the router isn't yet mounted (sanity check)**

Run: `cd backend && pytest tests/integration/test_pods_api.py -v`
Expected: PASS already (Task 8 wired it directly) — if `app/main.py` was left unmodified in Task 8, this step instead confirms 404s. Since Task 8's own tests require the router mounted to pass, `app/main.py` must already include it; this task's only remaining job is verifying `app/main.py` cleanly imports both routers together.

- [ ] **Step 2: Confirm `app/main.py` includes both routers**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.routers import events, pods

app = FastAPI(title="OpenTourney")
app.include_router(events.router)
app.include_router(pods.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 3: Run the full backend test suite + lint**

Run: `cd backend && pytest -v && ruff check app tests`
Expected: PASS, no lint errors

- [ ] **Step 4: Commit (only if `main.py` needed a change beyond Task 8)**

```bash
cd backend
git add app/main.py
git commit -m "chore: confirm events and pods routers are both mounted"
```

**End of PR2.** Open the PR, run `/code-review`, then manual verification: print a checklist (create event as organizer / non-organizer rejected / read by unrelated identity rejected / update+delete / one-pod-per-event 409) and exercise each with `curl` or the test suite's equivalent against a locally running `uvicorn` + testcontainers-backed Postgres before asking to merge.

---

## PR 3 — Entries + GameModule wiring + pod-role assignment

**Branch:** create fresh off `main` after PR2 merges — `feat/phase-5c-entries-gamemodule-roles`.

### Task 10: Game module registry

**Files:**
- Create: `backend/app/games/registry.py`
- Test: `backend/tests/unit/test_games_registry.py`

**Interfaces:**
- Produces: `app.games.registry.GAME_MODULES: dict[str, GameModule]`; `app.games.registry.get_game_module(slug: str) -> GameModule` (raises `ValueError` for an unknown slug).
- Consumes: `app.games.base.GameModule`, `app.games.generic.GenericGameModule` (Phase 4, existing).

- [ ] **Step 1: Write the failing unit test**

```python
# backend/tests/unit/test_games_registry.py
import pytest

from app.games.generic import GenericGameModule
from app.games.registry import get_game_module


def test_get_game_module_returns_generic_module():
    module = get_game_module("generic")

    assert isinstance(module, GenericGameModule)


def test_get_game_module_raises_for_unknown_slug():
    with pytest.raises(ValueError, match="unknown game module slug"):
        get_game_module("pokemon-tcg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_games_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.games.registry'`

- [ ] **Step 3: Write `app/games/registry.py`**

```python
# backend/app/games/registry.py
from app.games.base import GameModule
from app.games.generic import GenericGameModule

GAME_MODULES: dict[str, GameModule] = {
    "generic": GenericGameModule(),
}


def get_game_module(slug: str) -> GameModule:
    try:
        return GAME_MODULES[slug]
    except KeyError:
        raise ValueError(f"unknown game module slug: {slug!r}") from None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_games_registry.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/games/registry.py tests/unit/test_games_registry.py
git commit -m "feat: add game module registry"
```

---

### Task 11: Entry schemas + router (GameModule-validated)

**Files:**
- Create: `backend/app/schemas/entry.py`
- Create: `backend/app/routers/entries.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_entries_api.py`

**Interfaces:**
- Produces: `app.schemas.entry.EntryCreate(pod_id, player_uuid, source_system, metadata)`, `EntryUpdate(metadata)`, `EntryRead(id, pod_id, player_uuid, source_system, metadata)`; `app.routers.entries.router` (`APIRouter(prefix="/entries")`) with `POST /entries`, `GET /entries?pod_id=`, `GET /entries/{entry_id}`, `PATCH /entries/{entry_id}`, `DELETE /entries/{entry_id}`.
- Consumes: `app.games.registry.get_game_module` (Task 10); `app.auth.dependencies.event_organizer_exists`, `get_current_identity`, `pod_role_exists`, `require_pod_access` (Task 6); `app.models.Entry`, `Pod` (Phase 3).

- [ ] **Step 1: Write the failing integration tests**

```python
# backend/tests/integration/test_entries_api.py
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_pod(api_client, token) -> str:
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]
    return api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]


def test_organizer_creates_entry(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    player_uuid = str(uuid.uuid4())

    response = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": player_uuid,
            "source_system": "club-checkin",
            "metadata": {"display_name": "Ash"},
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["metadata"] == {"display_name": "Ash"}


def test_non_organizer_cannot_create_entry(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_pod_role_can_read_entries_without_organizer_row(api_client, make_token, db_session):
    from app.models.rbac import PodRole

    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(owner_token),
    )

    reader_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=uuid.UUID(pod_id),
            player_uuid=reader_uuid,
            source_system="club-checkin",
            role="user",
        )
    )
    db_session.commit()
    reader_token = make_token(player_uuid=reader_uuid, source_system="club-checkin")

    response = api_client.get(
        "/entries", params={"pod_id": pod_id}, headers=_auth_headers(reader_token)
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_organizer_can_update_and_delete_entry(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/entries/{entry_id}",
        json={"metadata": {"display_name": "Misty"}},
        headers=_auth_headers(token),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["metadata"] == {"display_name": "Misty"}

    delete_response = api_client.delete(f"/entries/{entry_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_entries_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.entry'`

- [ ] **Step 3: Write `app/schemas/entry.py`**

```python
# backend/app/schemas/entry.py
import uuid

from pydantic import BaseModel, ConfigDict, Field


class EntryCreate(BaseModel):
    pod_id: uuid.UUID
    player_uuid: uuid.UUID
    source_system: str
    metadata: dict = {}


class EntryUpdate(BaseModel):
    metadata: dict


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pod_id: uuid.UUID
    player_uuid: uuid.UUID
    source_system: str
    metadata: dict = Field(validation_alias="metadata_")
```

- [ ] **Step 4: Write `app/routers/entries.py`**

```python
# backend/app/routers/entries.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    event_organizer_exists,
    get_current_identity,
    pod_role_exists,
    require_pod_access,
)
from app.auth.identity import Identity
from app.db import get_db_session
from app.games.registry import get_game_module
from app.models import Entry, Pod
from app.schemas.entry import EntryCreate, EntryRead, EntryUpdate

router = APIRouter(prefix="/entries", tags=["entries"])


@router.post("", response_model=EntryRead, status_code=201)
def create_entry(
    payload: EntryCreate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    pod = db.get(Pod, payload.pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    if not event_organizer_exists(db, identity, pod.event_id):
        raise HTTPException(
            status_code=403, detail="Organizer role required for this pod's event"
        )

    game_module = get_game_module(pod.game_slug)
    try:
        game_module.validate_entry_metadata(payload.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry = Entry(
        pod_id=payload.pod_id,
        player_uuid=payload.player_uuid,
        source_system=payload.source_system,
        metadata_=payload.metadata,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=list[EntryRead])
def list_entries(
    pod_id: uuid.UUID = Query(...),
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> list[Entry]:
    return db.query(Entry).filter_by(pod_id=pod_id).all()


@router.get("/{entry_id}", response_model=EntryRead)
def get_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    pod = db.get(Pod, entry.pod_id)
    if not (
        event_organizer_exists(db, identity, pod.event_id)
        or pod_role_exists(db, identity, entry.pod_id)
    ):
        raise HTTPException(status_code=403, detail="no role scoped to this entry's pod")
    return entry


@router.patch("/{entry_id}", response_model=EntryRead)
def update_entry(
    entry_id: uuid.UUID,
    payload: EntryUpdate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    pod = db.get(Pod, entry.pod_id)
    if not event_organizer_exists(db, identity, pod.event_id):
        raise HTTPException(
            status_code=403, detail="Organizer role required for this entry's pod's event"
        )

    game_module = get_game_module(pod.game_slug)
    try:
        game_module.validate_entry_metadata(payload.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry.metadata_ = payload.metadata
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> None:
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    pod = db.get(Pod, entry.pod_id)
    if not event_organizer_exists(db, identity, pod.event_id):
        raise HTTPException(
            status_code=403, detail="Organizer role required for this entry's pod's event"
        )
    db.delete(entry)
    db.commit()
```

- [ ] **Step 5: Wire the router into `app/main.py`**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.routers import entries, events, pods

app = FastAPI(title="OpenTourney")
app.include_router(events.router)
app.include_router(pods.router)
app.include_router(entries.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_entries_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/schemas/entry.py app/routers/entries.py app/main.py tests/integration/test_entries_api.py
git commit -m "feat: add Entries CRUD endpoints with GameModule validation"
```

---

### Task 12: Pod-role assignment schemas + router

**Files:**
- Create: `backend/app/schemas/pod_role.py`
- Create: `backend/app/routers/pod_roles.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_pod_roles_api.py`

**Interfaces:**
- Produces: `app.schemas.pod_role.PodRoleCreate(player_uuid, source_system, role)`, `PodRoleRead(id, pod_id, player_uuid, source_system, role)`; `app.routers.pod_roles.router` (`APIRouter(prefix="/pods/{pod_id}/roles")`) with `POST`, `GET`, `DELETE /{role_id}` — this is what makes `PodRole` rows (consumed since Task 6) actually grantable by an Organizer.
- Consumes: `app.auth.dependencies.require_pod_organizer` (Task 6); `app.models.rbac.PodRole`, `PodRoleName` (Task 2).

- [ ] **Step 1: Write the failing integration tests**

```python
# backend/tests/integration/test_pod_roles_api.py
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_pod(api_client, token) -> str:
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]
    return api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]


def test_organizer_assigns_scorekeeper_role(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    scorekeeper_uuid = str(uuid.uuid4())

    response = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": scorekeeper_uuid,
            "source_system": "club-checkin",
            "role": "scorekeeper",
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["role"] == "scorekeeper"


def test_non_organizer_cannot_assign_roles(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "user",
        },
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_duplicate_role_assignment_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    identity_uuid = str(uuid.uuid4())
    api_client.post(
        f"/pods/{pod_id}/roles",
        json={"player_uuid": identity_uuid, "source_system": "club-checkin", "role": "user"},
        headers=_auth_headers(token),
    )

    response = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": identity_uuid,
            "source_system": "club-checkin",
            "role": "scorekeeper",
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_organizer_can_list_and_revoke_role(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    role_id = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "user",
        },
        headers=_auth_headers(token),
    ).json()["id"]

    list_response = api_client.get(f"/pods/{pod_id}/roles", headers=_auth_headers(token))
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    delete_response = api_client.delete(
        f"/pods/{pod_id}/roles/{role_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 204

    list_after_response = api_client.get(f"/pods/{pod_id}/roles", headers=_auth_headers(token))
    assert list_after_response.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_pod_roles_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.pod_role'`

- [ ] **Step 3: Write `app/schemas/pod_role.py`**

```python
# backend/app/schemas/pod_role.py
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.rbac import PodRoleName


class PodRoleCreate(BaseModel):
    player_uuid: uuid.UUID
    source_system: str
    role: PodRoleName


class PodRoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pod_id: uuid.UUID
    player_uuid: uuid.UUID
    source_system: str
    role: PodRoleName
```

- [ ] **Step 4: Write `app/routers/pod_roles.py`**

```python
# backend/app/routers/pod_roles.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_pod_organizer
from app.auth.identity import Identity
from app.db import get_db_session
from app.models.rbac import PodRole
from app.schemas.pod_role import PodRoleCreate, PodRoleRead

router = APIRouter(prefix="/pods/{pod_id}/roles", tags=["pod-roles"])


@router.post("", response_model=PodRoleRead, status_code=201)
def assign_pod_role(
    pod_id: uuid.UUID,
    payload: PodRoleCreate,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> PodRole:
    existing = (
        db.query(PodRole)
        .filter_by(
            pod_id=pod_id,
            player_uuid=payload.player_uuid,
            source_system=payload.source_system,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="this identity already has a role on this pod"
        )

    role = PodRole(
        pod_id=pod_id,
        player_uuid=payload.player_uuid,
        source_system=payload.source_system,
        role=payload.role,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.get("", response_model=list[PodRoleRead])
def list_pod_roles(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> list[PodRole]:
    return db.query(PodRole).filter_by(pod_id=pod_id).all()


@router.delete("/{role_id}", status_code=204)
def revoke_pod_role(
    pod_id: uuid.UUID,
    role_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> None:
    role = db.get(PodRole, role_id)
    if role is None or role.pod_id != pod_id:
        raise HTTPException(status_code=404, detail="pod role not found")
    db.delete(role)
    db.commit()
```

- [ ] **Step 5: Wire the router into `app/main.py`**

```python
# backend/app/main.py
from fastapi import FastAPI

from app.routers import entries, events, pod_roles, pods

app = FastAPI(title="OpenTourney")
app.include_router(events.router)
app.include_router(pods.router)
app.include_router(entries.router)
app.include_router(pod_roles.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_pod_roles_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Run the full backend test suite + lint**

Run: `cd backend && pytest -v && ruff check app tests`
Expected: PASS, no lint errors

- [ ] **Step 8: Commit**

```bash
cd backend
git add app/schemas/pod_role.py app/routers/pod_roles.py app/main.py tests/integration/test_pod_roles_api.py
git commit -m "feat: add pod-role assignment endpoints"
```

**End of PR3.** Open the PR, run `/code-review`, then manual verification: checklist covering entry creation (organizer/non-organizer), GameModule validation being invoked (confirm via a deliberately malformed-but-currently-always-valid generic payload, noting the generic module accepts anything by design), role assignment granting pod access to a non-organizer identity, and duplicate-role-assignment rejection — before asking to merge.

---

## PR 4 — OpenAPI publish + Helm/staging wiring + manual verification

**Branch:** create fresh off `main` after PR3 merges — `feat/phase-5d-openapi-helm-verification`.

PR1's final whole-branch review found two items scoped for "before PR4's staging deploy" (issue #17, Important) and general auth/RBAC test-coverage polish (issue #16, Minor) — both slot in first, before the OpenAPI/Helm/staging-verification work, since #17 changes how `app/main.py` constructs itself and #16 touches files (`app/db.py`, `app/auth/jwks.py`, `app/auth/identity.py`, `tests/support/`) that later tasks build on.

### Task 13: Fix #16 — auth/RBAC test coverage & polish

**Files:**
- Modify: `backend/app/db.py` (return type annotation)
- Modify: `backend/tests/unit/test_config.py` (add `get_settings()` coverage)
- Modify: `backend/tests/integration/test_rbac_models.py` (add `PodRole` FK + invalid-enum tests)
- Modify: `backend/tests/support/jwt_helpers.py` (return annotation + docstrings)
- Modify: `backend/tests/unit/test_jwks.py` (add `RemoteJWKSProvider` delegation test)
- Modify: `backend/tests/unit/test_identity.py` (add non-UUID `sub` test)
- Create: `backend/tests/support/fake_jwks.py`
- Modify: `backend/tests/unit/test_oidc.py` (use the shared fake instead of a local copy)
- Modify: `backend/tests/integration/test_auth_dependencies.py` (use the shared fake instead of a local copy)
- Modify: `backend/tests/integration/conftest.py` (`test_keypair` → session-scoped)

**Interfaces:** none new — this task is test coverage and cosmetic fixes only, no behavior changes to any production code path except `get_engine`'s added return annotation (purely a type hint, no runtime change).

- [ ] **Step 1: `get_engine()` return type annotation**

```python
# backend/app/db.py
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_db_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
```

- [ ] **Step 2: Add `get_settings()` env-var-reading test coverage**

```python
# backend/tests/unit/test_config.py (append)
import pytest

from app.config import get_settings


def test_get_settings_reads_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db")
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("OIDC_AUDIENCE", "aud")
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    monkeypatch.delenv("OIDC_JWKS_STATIC", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url == "postgresql+psycopg://u:p@host/db"
    assert settings.oidc_issuer == "https://issuer.example.com"
    assert settings.oidc_audience == "aud"
    assert settings.oidc_jwks_url is None
    assert settings.oidc_jwks_static is None

    get_settings.cache_clear()


def test_get_settings_raises_key_error_when_a_required_var_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("OIDC_AUDIENCE", "aud")
    get_settings.cache_clear()

    with pytest.raises(KeyError):
        get_settings()

    get_settings.cache_clear()
```

Run: `cd backend && pytest tests/unit/test_config.py -v`
Expected: PASS (5 tests — 3 existing + 2 new)

- [ ] **Step 3: `PodRole` FK + invalid-enum-value tests**

```python
# backend/tests/integration/test_rbac_models.py (append)
from sqlalchemy.exc import DataError


def test_pod_role_requires_existing_pod(db_session):
    db_session.add(
        PodRole(
            pod_id=uuid.uuid4(),
            player_uuid=uuid.uuid4(),
            source_system="club-checkin",
            role=PodRoleName.USER,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_pod_role_rejects_invalid_role_value(db_session):
    event = _make_event(db_session)
    pod = _make_pod(db_session, event)

    db_session.execute(
        text(
            "INSERT INTO pod_roles (id, pod_id, player_uuid, source_system, role) "
            "VALUES (gen_random_uuid(), :pod_id, gen_random_uuid(), 'club-checkin', 'not-a-real-role')"
        ),
        {"pod_id": pod.id},
    )
    with pytest.raises(DataError):
        db_session.commit()
```

Add `from sqlalchemy import text` to the file's existing import block. `pod_roles.role` is a Postgres enum type — raising a plain `PodRole(role="not-a-real-role")` through the ORM would fail at the Python `Enum`/`values_callable` layer before ever reaching the DB, which wouldn't actually test the DB-level constraint; a raw `INSERT` is the only way to exercise the enum type itself. `gen_random_uuid()` requires no extra extension on Postgres 16 (built in since PG13).

Run: `cd backend && pytest tests/integration/test_rbac_models.py -v`
Expected: PASS (8 tests — 6 existing + 2 new)

- [ ] **Step 4: `jwt_helpers.py` return annotation + docstrings**

```python
# backend/tests/support/jwt_helpers.py
import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jwt.algorithms import RSAAlgorithm


def generate_test_keypair(kid: str = "test-key") -> tuple[RSAPrivateKey, str]:
    """Generate a real RSA keypair and its public JWK set (as JSON) for signing test tokens."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk["kid"] = kid
    public_jwk["use"] = "sig"
    public_jwk["alg"] = "RS256"
    jwks_json = json.dumps({"keys": [public_jwk]})
    return private_key, jwks_json


def mint_token(
    private_key,
    *,
    kid: str,
    issuer: str,
    audience: str,
    player_uuid: uuid.UUID | str,
    source_system: str,
    roles: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """Sign a JWT with the given private key, shaped like OpenTourney's expected OIDC assertion."""
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": str(player_uuid),
        "source_system": source_system,
        "roles": roles or [],
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
```

- [ ] **Step 5: `RemoteJWKSProvider` delegation test**

```python
# backend/tests/unit/test_jwks.py (append)
from unittest.mock import MagicMock, patch

from app.auth.jwks import RemoteJWKSProvider


def test_remote_provider_delegates_to_pyjwk_client():
    # The only legitimate use of mocking in this codebase: RemoteJWKSProvider is a thin
    # wrapper around a third-party network client (PyJWKClient), not business logic —
    # every other test in this project exercises real crypto/DB behavior, never mocks.
    fake_signing_key = MagicMock()
    with patch("app.auth.jwks.PyJWKClient") as mock_client_cls:
        mock_client_cls.return_value.get_signing_key_from_jwt.return_value = fake_signing_key

        provider = RemoteJWKSProvider("https://issuer.example.com/.well-known/jwks.json")
        result = provider.get_signing_key("some-token")

        mock_client_cls.assert_called_once_with(
            "https://issuer.example.com/.well-known/jwks.json"
        )
        mock_client_cls.return_value.get_signing_key_from_jwt.assert_called_once_with(
            "some-token"
        )
        assert result is fake_signing_key
```

Run: `cd backend && pytest tests/unit/test_jwks.py -v`
Expected: PASS (5 tests — 4 existing + 1 new)

- [ ] **Step 6: `identity_from_claims` non-UUID `sub` test**

```python
# backend/tests/unit/test_identity.py (append)
def test_identity_from_claims_raises_for_non_uuid_sub():
    with pytest.raises(AuthError):
        identity_from_claims(
            {"sub": "not-a-uuid", "source_system": "club-checkin", "roles": []}
        )
```

Run: `cd backend && pytest tests/unit/test_identity.py -v`
Expected: PASS (8 tests — 7 existing + 1 new)

- [ ] **Step 7: Extract the duplicated JWKS-failure test double into a shared helper**

```python
# backend/tests/support/fake_jwks.py
import jwt


class FakeUnreachableJWKSProvider:
    """Simulates a JWKS source (e.g. the IdP) that cannot be reached over the network."""

    def get_signing_key(self, token: str):
        raise jwt.PyJWKClientConnectionError("simulated JWKS fetch failure")
```

In `backend/tests/unit/test_oidc.py`: delete the local `class _FakeUnreachableJWKSProvider` definition, add `from tests.support.fake_jwks import FakeUnreachableJWKSProvider` to the imports, and replace the one usage (`_FakeUnreachableJWKSProvider()`) with `FakeUnreachableJWKSProvider()`.

In `backend/tests/integration/test_auth_dependencies.py`: same change — delete the local class, import `FakeUnreachableJWKSProvider` from `tests.support.fake_jwks`, replace the one usage.

Run: `cd backend && pytest tests/unit/test_oidc.py tests/integration/test_auth_dependencies.py -v`
Expected: PASS (both files, same counts as before — behavior unchanged, only the class's location moved)

- [ ] **Step 8: Session-scope the `test_keypair` fixture**

```python
# backend/tests/integration/conftest.py
@pytest.fixture(scope="session")
def test_keypair():
    return generate_test_keypair()
```

(Change only the decorator on the existing `test_keypair` fixture — from `@pytest.fixture()` to `@pytest.fixture(scope="session")`. `test_settings`/`make_token` stay function-scoped; they still each construct their own `Settings`/token per test, just built from one shared keypair instead of a fresh one per test. Safe because `Settings` and the key are never mutated, and every test in `tests/unit/` calls `generate_test_keypair()` directly rather than through this fixture, so they're unaffected.)

- [ ] **Step 9: Run the full backend test suite + lint**

Run: `cd backend && pytest -v && ruff check app tests`
Expected: PASS, no lint errors

- [ ] **Step 10: Commit**

```bash
cd backend
git add app/db.py tests/unit/test_config.py tests/integration/test_rbac_models.py \
  tests/support/jwt_helpers.py tests/support/fake_jwks.py tests/unit/test_jwks.py \
  tests/unit/test_identity.py tests/unit/test_oidc.py tests/integration/test_auth_dependencies.py \
  tests/integration/conftest.py
git commit -m "test: close auth/RBAC coverage gaps and dedupe JWKS test double (closes #16)"
```

---

### Task 14: Fix #17 — fail-fast config validation via FastAPI lifespan

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_main_lifespan.py`

**Interfaces:**
- Produces: a `lifespan` context manager on `app.main.app` that eagerly resolves `Settings` and builds the `JWKSProvider` at ASGI startup, before any request is served.
- Consumes: `app.config.get_settings` (Task 1), `app.auth.jwks.build_jwks_provider` (Task 4, already `@lru_cache`d — the lifespan call populates that cache once at boot; every later `Depends(get_jwks_provider)` during a request just returns the cached instance).

The key design constraint: this must not break any existing test's `app.dependency_overrides[get_settings] = lambda: test_settings` pattern (used throughout PR2/PR3's `api_client` fixture and PR1's `test_auth_dependencies.py`). A lifespan function that called the real `get_settings()` directly would bypass overrides entirely (`dependency_overrides` only intercepts `Depends(...)` resolution during request handling, not arbitrary direct calls) and break every existing integration test, since none of them set real `DATABASE_URL`/`OIDC_*` environment variables. The fix: have `lifespan` check `app.dependency_overrides` itself before falling back to the real function — the same dict FastAPI's own resolver consults.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_main_lifespan.py
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_lifespan_eagerly_resolves_settings_at_startup(monkeypatch):
    calls = []

    def spy_get_settings():
        calls.append(True)
        raise KeyError("DATABASE_URL")  # short-circuits before build_jwks_provider runs

    monkeypatch.setattr("app.main.get_settings", spy_get_settings)

    with pytest.raises(KeyError):
        with TestClient(app):
            pass

    assert calls, "lifespan should call get_settings() at startup, before serving any request"


def test_lifespan_respects_dependency_overrides(test_settings):
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        with TestClient(app):
            pass  # must not raise — test_settings carries a valid static JWKS
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_main_lifespan.py -v`
Expected: FAIL — `test_lifespan_eagerly_resolves_settings_at_startup` fails because nothing calls `get_settings()` at startup yet (no `KeyError` raised, `calls` stays empty)

- [ ] **Step 3: Add the lifespan handler to `app/main.py`**

```python
# backend/app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.jwks import build_jwks_provider
from app.config import get_settings
from app.routers import entries, events, pod_roles, pods


@asynccontextmanager
async def lifespan(app: FastAPI):
    resolve_settings = app.dependency_overrides.get(get_settings, get_settings)
    settings = resolve_settings()
    build_jwks_provider(settings)
    yield


app = FastAPI(title="OpenTourney", lifespan=lifespan)
app.include_router(events.router)
app.include_router(pods.router)
app.include_router(entries.router)
app.include_router(pod_roles.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

Scope note: `build_jwks_provider` validates that *some* JWKS source is configured (raises `RuntimeError` if neither `OIDC_JWKS_STATIC` nor `OIDC_JWKS_URL` is set) and, for the static path, parses the JWK set immediately — both real boot-time failures. For the remote path, `PyJWKClient` itself fetches lazily (on first `get_signing_key_from_jwt` call, not at construction), so an unreachable-but-configured `OIDC_JWKS_URL` still won't be caught until the first real request — that's a `PyJWKClient` behavior this task doesn't change, and forcing an eager fetch at every boot would add startup latency for a check that's better handled by the existing `AuthServiceUnavailableError` → 503 mapping (PR1) anyway.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_main_lifespan.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full backend test suite + lint**

Run: `cd backend && pytest -v && ruff check app tests`
Expected: PASS, no lint errors — this is the critical check for this task: every existing PR2/PR3 router test uses `api_client`, which triggers this same lifespan on every `with TestClient(...)`, so a regression here would fail broadly, not just in the new test file.

- [ ] **Step 6: Commit**

```bash
cd backend
git add app/main.py tests/integration/test_main_lifespan.py
git commit -m "feat: fail fast on misconfiguration at startup instead of first request (closes #17)"
```

---

### Task 15: Versioned OpenAPI export + drift test

**Files:**
- Modify: `backend/app/main.py` (set `version=` from package metadata)
- Create: `backend/scripts/export_openapi.py`
- Create: `docs/openapi.json` (generated, then committed)
- Test: `backend/tests/unit/test_openapi_spec.py`

**Interfaces:**
- Produces: `docs/openapi.json` (committed snapshot of `app.openapi()`), `backend/scripts/export_openapi.py` (regenerates it).
- Consumes: `app.main.app` (all prior routers).

- [ ] **Step 1: Set the app version from package metadata**

Task 14 already added the `lifespan` handler — this step only adds `version=`, keeping everything else as Task 14 left it:

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI

from app.auth.jwks import build_jwks_provider
from app.config import get_settings
from app.routers import entries, events, pod_roles, pods


@asynccontextmanager
async def lifespan(app: FastAPI):
    resolve_settings = app.dependency_overrides.get(get_settings, get_settings)
    settings = resolve_settings()
    build_jwks_provider(settings)
    yield


app = FastAPI(
    title="OpenTourney",
    version=_pkg_version("opentourney-backend"),
    lifespan=lifespan,
)
app.include_router(events.router)
app.include_router(pods.router)
app.include_router(entries.router)
app.include_router(pod_roles.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 2: Write the export script**

```python
# backend/scripts/export_openapi.py
#!/usr/bin/env python3
import json
from pathlib import Path

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "docs" / "openapi.json"


def main() -> None:
    spec = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Generate the initial committed spec**

Run: `cd backend && pip install -e ".[dev]" && python scripts/export_openapi.py`
Expected: `wrote .../docs/openapi.json`

- [ ] **Step 4: Write the failing drift test**

```python
# backend/tests/unit/test_openapi_spec.py
import json
from pathlib import Path

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMITTED_SPEC_PATH = REPO_ROOT / "docs" / "openapi.json"


def test_committed_openapi_spec_matches_generated_spec():
    generated = app.openapi()
    committed = json.loads(COMMITTED_SPEC_PATH.read_text())

    assert generated == committed, (
        "docs/openapi.json is out of date — regenerate it with "
        "`python scripts/export_openapi.py` from backend/ and commit the result"
    )


def test_app_version_matches_installed_package_version():
    from importlib.metadata import version

    assert app.version == version("opentourney-backend")
```

Note: this test should already pass immediately after Step 3 generates the file — it exists to *stay* green (catch future drift), not to drive new implementation. Confirm this explicitly rather than treating "already green" as a skip.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_openapi_spec.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full backend test suite + lint**

Run: `cd backend && pytest -v && ruff check app tests`
Expected: PASS, no lint errors

- [ ] **Step 7: Commit**

```bash
cd backend
git add app/main.py scripts/export_openapi.py tests/unit/test_openapi_spec.py ../docs/openapi.json
git commit -m "feat: publish a versioned, drift-checked OpenAPI spec"
```

---

### Task 16: Docs site link

**Files:**
- Modify: `docs/conf.py`
- Modify: `docs/index.rst`

**Interfaces:** none (documentation-only; no code interfaces).

- [ ] **Step 1: Add `openapi.json` to Sphinx's extra static files**

```python
# docs/conf.py
project = "OpenTourney"
copyright = "2026, BadConfigStudios"
author = "BadConfigStudios"
release = "0.1.0"

extensions = ["sphinx.ext.autodoc"]

templates_path = ["_templates"]
exclude_patterns = ["_build"]
html_extra_path = ["openapi.json"]

html_theme = "alabaster"
```

- [ ] **Step 2: Link it from the docs home page**

```rst
OpenTourney
===========

Game-agnostic, open tournament-tracking standard and engine.

`Download the OpenAPI spec (JSON) <openapi.json>`_

.. toctree::
   :maxdepth: 2
```

- [ ] **Step 3: Build the docs to verify the link resolves**

Run: `cd backend && sphinx-build -b html ../docs ../docs/_build -W`
Expected: build succeeds; `docs/_build/openapi.json` exists

- [ ] **Step 4: Commit**

```bash
git add docs/conf.py docs/index.rst
git commit -m "docs: link the published OpenAPI spec from the docs site"
```

---

### Task 17: Helm chart — secrets + env wiring

**Files:**
- Create: `charts/opentourney/templates/secret.yaml`
- Modify: `charts/opentourney/templates/deployment-backend.yaml`
- Modify: `charts/opentourney/values.yaml`

**Interfaces:** none (infra-only; no application code interfaces). Mirrors the existing `limitless-organizer-tracker` chart's `secret.yaml` + `envFrom.secretRef` pattern (same deploy target, same convention already logged in `DECISIONS.md`).

- [ ] **Step 1: Add the Secret template**

```yaml
# charts/opentourney/templates/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "ot.fullname" . }}-secrets
  labels:
    {{- include "ot.labels" . | nindent 4 }}
type: Opaque
stringData:
  DATABASE_URL: {{ .Values.secrets.databaseUrl | quote }}
  OIDC_ISSUER: {{ .Values.secrets.oidcIssuer | quote }}
  OIDC_AUDIENCE: {{ .Values.secrets.oidcAudience | quote }}
  {{- if .Values.secrets.oidcJwksUrl }}
  OIDC_JWKS_URL: {{ .Values.secrets.oidcJwksUrl | quote }}
  {{- end }}
  {{- if .Values.secrets.oidcJwksStatic }}
  OIDC_JWKS_STATIC: {{ .Values.secrets.oidcJwksStatic | quote }}
  {{- end }}
```

- [ ] **Step 2: Wire `envFrom` into the backend Deployment**

Add to `charts/opentourney/templates/deployment-backend.yaml`, inside the `backend` container spec (after `imagePullPolicy`, before `ports`):

```yaml
          envFrom:
            - secretRef:
                name: {{ include "ot.fullname" . }}-secrets
```

- [ ] **Step 3: Add the `secrets` placeholder block to `values.yaml`**

Append to `charts/opentourney/values.yaml`:

```yaml
secrets:
  databaseUrl: ""
  oidcIssuer: ""
  oidcAudience: ""
  oidcJwksUrl: ""
  oidcJwksStatic: ""
```

- [ ] **Step 4: Lint the chart**

Run: `helm lint charts/opentourney`
Expected: no errors (real secret values are supplied at deploy time via `--set`, matching `limitless-organizer-tracker`'s existing staging workflow — never committed)

- [ ] **Step 5: Commit**

```bash
git add charts/opentourney/templates/secret.yaml charts/opentourney/templates/deployment-backend.yaml charts/opentourney/values.yaml
git commit -m "feat: wire DATABASE_URL and OIDC settings into the backend Deployment"
```

---

### Task 18: Staging test-token minting script

**Files:**
- Create: `backend/scripts/mint_test_token.py`
- Test: `backend/tests/unit/test_mint_test_token.py`

**Interfaces:**
- Produces: `scripts.mint_test_token.mint_token(private_key, *, kid, issuer, audience, player_uuid, source_system, roles=None, expires_in=3600) -> str` (standalone copy — deliberately not shared with `tests/support/jwt_helpers.py`, since one is test infra and the other an ops CLI with its own argument-parsing concerns; duplicating ~15 lines is cheaper than cross-importing `scripts/` into `tests/`).
- Consumes: `pyjwt` (already a dependency, Task 3/PR1).

- [ ] **Step 1: Write the failing unit test**

```python
# backend/tests/unit/test_mint_test_token.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import jwt

from mint_test_token import mint_token
from tests.support.jwt_helpers import generate_test_keypair


def test_mint_token_produces_a_verifiable_token():
    private_key, jwks_json = generate_test_keypair(kid="staging-key")

    token = mint_token(
        private_key,
        kid="staging-key",
        issuer="https://staging-issuer.example.com",
        audience="opentourney-staging",
        player_uuid="22222222-2222-2222-2222-222222222222",
        source_system="manual-verification",
        roles=["organizer"],
    )

    signing_key = jwt.PyJWKSet.from_json(jwks_json).keys[0]
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience="opentourney-staging",
        issuer="https://staging-issuer.example.com",
    )
    assert claims["roles"] == ["organizer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_mint_test_token.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mint_test_token'`

- [ ] **Step 3: Write `scripts/mint_test_token.py`**

```python
# backend/scripts/mint_test_token.py
#!/usr/bin/env python3
import argparse
import time
import uuid

import jwt


def mint_token(
    private_key,
    *,
    kid: str,
    issuer: str,
    audience: str,
    player_uuid: str,
    source_system: str,
    roles: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": str(player_uuid),
        "source_system": source_system,
        "roles": roles or [],
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mint a test OIDC token for manual staging verification."
    )
    parser.add_argument("--private-key-path", required=True, help="Path to a PEM RSA private key")
    parser.add_argument("--kid", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--audience", required=True)
    parser.add_argument("--player-uuid", default=str(uuid.uuid4()))
    parser.add_argument("--source-system", default="manual-verification")
    parser.add_argument("--organizer", action="store_true", help="include the organizer claim")
    args = parser.parse_args()

    with open(args.private_key_path, "rb") as key_file:
        private_key_pem = key_file.read()

    token = mint_token(
        private_key_pem,
        kid=args.kid,
        issuer=args.issuer,
        audience=args.audience,
        player_uuid=args.player_uuid,
        source_system=args.source_system,
        roles=["organizer"] if args.organizer else [],
    )
    print(token)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_mint_test_token.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Run the full backend test suite + lint**

Run: `cd backend && pytest -v && ruff check app tests scripts`
Expected: PASS, no lint errors

- [ ] **Step 6: Commit**

```bash
cd backend
git add scripts/mint_test_token.py tests/unit/test_mint_test_token.py
git commit -m "feat: add staging test-token minting script"
```

---

### Task 19: Manual verification against staging (mandatory pre-merge gate)

Per the mandatory manual-verification gate: build and push images from this branch, deploy to the `opentourney-staging` namespace on the cube cluster (staging-before-main-merge workflow), run migrations, generate a one-time staging test keypair, then work through this checklist and report pass/fail per item before asking to merge.

**One-time staging test-keypair setup** (private key never committed — keep it local or in a password manager):

```bash
openssl genrsa -out /tmp/staging-test-key.pem 2048
openssl rsa -in /tmp/staging-test-key.pem -pubout -out /tmp/staging-test-key-pub.pem
python3 - <<'EOF'
import json
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm

with open("/tmp/staging-test-key-pub.pem", "rb") as f:
    public_key = serialization.load_pem_public_key(f.read())

jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
jwk["kid"] = "staging-test-key"
jwk["use"] = "sig"
jwk["alg"] = "RS256"
print(json.dumps({"keys": [jwk]}))
EOF
```

Pass the printed JSON as `--set-string secrets.oidcJwksStatic='...'` on the staging `helm upgrade`, along with `secrets.databaseUrl`, `secrets.oidcIssuer=https://staging-issuer.example.com`, `secrets.oidcAudience=opentourney-staging`.

- [ ] Run `alembic upgrade head` via `kubectl exec` into the backend pod (`DATABASE_URL` already in its env from the Secret) and confirm no errors
- [ ] `POST /events` with no `Authorization` header → expect `403`
- [ ] `POST /events` with a token minted via `mint_test_token.py` (no `--organizer`) → expect `403`
- [ ] `POST /events` with a token minted via `mint_test_token.py --organizer` → expect `201`, capture `event_id`
- [ ] `GET /events/{event_id}` with the creator's token → expect `200`
- [ ] `GET /events/{event_id}` with a different `--player-uuid` token (no role) → expect `403`
- [ ] `POST /pods` with the creator's token → expect `201`, capture `pod_id`
- [ ] `POST /pods` again for the same `event_id` → expect `409`
- [ ] `POST /pods/{pod_id}/roles` assigning `role=user` to a fresh `--player-uuid` → expect `201`
- [ ] `POST /entries` as the event organizer with `metadata={}` → expect `201`
- [ ] `GET /entries?pod_id={pod_id}` using the newly role-assigned "user" identity's token (no organizer row) → expect `200`
- [ ] `DELETE /entries/{entry_id}` using that same "user" identity's token → expect `403`
- [ ] `GET /openapi.json` on staging → expect `200`, `info.version` matches the deployed package version
- [ ] `GET /docs` (Swagger UI) loads in a browser and lists all Phase 5 endpoints with their auth requirements visible

Fix any findings with follow-up commits on this branch before merging.

**End of PR4 and Phase 5.** Once PR4 is approved, manually verified, and merged (never merge without explicit in-the-moment approval), close GitHub issues #5, #16 (Task 13), and #17 (Task 14), delete the branch, and output the next-phase prompt for Phase 6 (Match & tournament reporting) per the standard phase-completion trigger.
