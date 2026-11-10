"""Shared test fixtures.

Every test runs with:
- no ANTHROPIC_API_KEY (tests must never need a real key),
- network sockets blocked (tests must never call the internet),
- its own temporary data folder (tests never touch real data).
"""

import socket

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a network connection."""


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    # Loopback must stay allowed: on Windows, asyncio's event loop connects a
    # socket pair to 127.0.0.1 internally. Everything else is blocked.
    real_connect = socket.socket.connect

    def guarded_connect(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK_HOSTS:
            raise NetworkBlockedError(f"Network access is blocked in tests: {address}")
        return real_connect(sock, address)

    def guarded_create_connection(address, *args, **kwargs):
        raise NetworkBlockedError(f"Network access is blocked in tests: {address}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client
