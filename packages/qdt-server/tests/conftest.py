"""A server over a temp registry with the stream on a free port; the simulated backend only."""

import pytest
from fastapi.testclient import TestClient

from qdt_server import Settings, create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(root=tmp_path / "registry", stream_port=0))
    with TestClient(app) as c:
        yield c
