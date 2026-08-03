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
