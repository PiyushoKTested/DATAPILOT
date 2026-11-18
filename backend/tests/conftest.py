"""Pytest fixtures and shared test helpers.

IMPORTANT: environment variables are set at *module import time* here, before any
test module imports the `app` package. conftest.py is imported by pytest before
test collection, so this guarantees `app.config.settings` is created once with
the correct test values.

An earlier version set the env inside a fixture and deleted `app.*` from
sys.modules to force re-import. That produced two distinct copies of every
module (test modules held references to the old ones, `app.main` re-imported new
ones), which silently broke `pytest.raises(SomeError)` because the raised class
and the expected class were different objects. Do not reintroduce that pattern.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Isolated environment — must run before `app` is imported anywhere.
# ---------------------------------------------------------------------------
_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="datapilot_tests_"))

os.environ["DATAPILOT_DATABASE_URL"] = f"sqlite:///{_TEMP_ROOT / 'test.db'}"
os.environ["DATAPILOT_DATA_DIR"] = str(_TEMP_ROOT)
os.environ["DATAPILOT_STORAGE_DIR"] = str(_TEMP_ROOT / "storage")
os.environ["DATAPILOT_REPORT_DIR"] = str(_TEMP_ROOT / "reports")
os.environ["DATAPILOT_CHART_DIR"] = str(_TEMP_ROOT / "charts")
os.environ["DATAPILOT_OLLAMA_ENABLED"] = "false"  # deterministic + offline
os.environ["DATAPILOT_SECRET_KEY"] = "test-secret-key-for-pytest-only-min-32-bytes"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    """Create the schema once for the whole test session."""
    from app.config import settings
    from app.database import init_db

    settings.ensure_dirs()
    init_db()
    yield


@pytest.fixture()
def sample_dir() -> Path:
    return BACKEND_DIR.parent / "sample_data"


@pytest.fixture()
def tiny_frame():
    from app.services.ingest import parse_upload

    path = BACKEND_DIR.parent / "sample_data" / "tiny_known.csv"
    return parse_upload(path.read_bytes(), path.name)


@pytest.fixture()
def sales_frame():
    from app.services.ingest import parse_upload

    path = BACKEND_DIR.parent / "sample_data" / "sales_data.csv"
    return parse_upload(path.read_bytes(), path.name)


@pytest.fixture()
def iris_frame():
    from app.services.ingest import parse_upload

    path = BACKEND_DIR.parent / "sample_data" / "iris.csv"
    return parse_upload(path.read_bytes(), path.name)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
