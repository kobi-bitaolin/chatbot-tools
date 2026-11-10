import os
import socket

import pytest

from tests.conftest import NetworkBlockedError


def test_ac_45_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ac_47_no_network_no_key(client):
    # No API key is available inside the test suite.
    assert "ANTHROPIC_API_KEY" not in os.environ

    # Any attempt to reach the network fails.
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("example.com", 80))

    # The app still starts and serves requests (the LLM client is created lazily).
    assert client.get("/health").status_code == 200
