"""A server over a temp registry with the stream on a free port; the simulated backend only."""

import pytest
from fastapi.testclient import TestClient

from qdt_registry import DSN_ENV, STORE_ENV
from qdt_server import Settings, create_app


@pytest.fixture(autouse=True)
def no_registry_server(monkeypatch):
    """No server from the developer's environment: a test's records never leave its temp dir (ADR 0080
    syncs after every run). A test that wants a server sets the two variables itself."""
    monkeypatch.delenv(DSN_ENV, raising=False)
    monkeypatch.delenv(STORE_ENV, raising=False)


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(root=tmp_path / "registry", stream_port=0))
    with TestClient(app) as c:
        yield c
