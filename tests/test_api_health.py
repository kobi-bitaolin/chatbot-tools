import os
import socket

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import NetworkBlockedError


def test_ac_45_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ac_47_no_network_no_key(settings):
    # No API key is available inside the test suite.
    assert "GEMINI_API_KEY" not in os.environ
    assert "GOOGLE_API_KEY" not in os.environ

    # Any attempt to reach the network fails.
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("example.com", 80))

    # The app, built with the REAL LLM client (no fake), still starts and
    # serves requests: the SDK client is only created on the first LLM call.
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
