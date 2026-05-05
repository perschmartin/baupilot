"""BauPilot — Pytest-Konfiguration."""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """FastAPI-Testclient."""
    with TestClient(app) as c:
        yield c
