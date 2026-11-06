"""Test app with an isolated temporary SQLite DB and media directory."""
import os
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="nextphase-test-"))
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///" + str(ROOT / "test.sqlite3")
os.environ["STORAGE_DIR"] = str(ROOT / "media")
os.environ["JWT_SECRET"] = "unit-test-private-key-unique-long-secret-12345"

import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
