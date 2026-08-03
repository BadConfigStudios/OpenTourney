import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from app.config import Settings, get_settings
from app.db import get_db_session
from app.main import app as fastapi_app
from tests.support.jwt_helpers import generate_test_keypair, mint_token

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
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="session")
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


@pytest.fixture()
def api_client(db_session, test_settings):
    def override_get_db_session():
        yield db_session

    fastapi_app.dependency_overrides[get_db_session] = override_get_db_session
    fastapi_app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(fastapi_app) as client:
        yield client

    fastapi_app.dependency_overrides.clear()
