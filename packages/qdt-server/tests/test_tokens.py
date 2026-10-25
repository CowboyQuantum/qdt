"""The command token (ADR 0074, 0082; Step 6c L0 row "Token"): a command from another computer is
refused without a token and accepted with one; reads and loopback are open; the file is the truth."""

import pytest
from fastapi.testclient import TestClient

from qdt_server import Settings, create_app
from qdt_server.auth import is_loopback, new_token, read_tokens
from qdt_sim.scenarios import stability

LOOPBACK = ("127.0.0.1", 50000)
"""This computer, as the test client's peer; the default peer, `testclient`, is not an address."""
ELSEWHERE = ("192.0.2.10", 50000)
"""Another computer: a documentation address (RFC 5737 TEST-NET-1), no real desk (rule 7)."""
NOWHERE = "0" * 32


def definition() -> dict:
    return stability(8, 8, p1=(0.03, 0.18), p2=(0.03, 0.18), name="token test").model_dump(
        mode="json"
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_commands_from_another_computer_need_a_token_from_the_file(tmp_path):
    settings = Settings(root=tmp_path / "registry", stream_port=0)
    token = new_token(settings.token_file, "desk by the window")
    with TestClient(create_app(settings), client=ELSEWHERE) as c:
        # reads are open to the network
        assert c.get("/stand").status_code == 200
        assert c.get("/levels").status_code == 200
        assert c.get("/runs").status_code == 200
        # a command without a token is refused, and the refusal says how to authenticate
        r = c.post("/sweeps/compile", json=definition())
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
        assert "Authorization: Bearer" in r.json()["detail"]
        assert c.delete("/levels").status_code == 401
        assert c.post("/runs", json={"definition": definition()}).status_code == 401
        # a wrong token, a wrong scheme and an empty bearer are refused too
        assert (
            c.post("/sweeps/compile", json=definition(), headers=bearer("nope")).status_code == 401
        )
        basic = {"Authorization": f"Basic {token}"}
        assert c.post("/sweeps/compile", json=definition(), headers=basic).status_code == 401
        assert c.post("/sweeps/compile", json=definition(), headers=bearer("")).status_code == 401
        # the token from the file is accepted, for every command
        assert (
            c.post("/sweeps/compile", json=definition(), headers=bearer(token)).status_code == 200
        )
        assert c.delete("/levels", headers=bearer(token)).status_code == 200
        # revoked by deleting its line: no restart
        settings.token_file.write_text("# every line removed\n", encoding="utf-8")
        assert (
            c.post("/sweeps/compile", json=definition(), headers=bearer(token)).status_code == 401
        )
        assert "removed" in c.delete("/levels", headers=bearer(token)).json()["detail"]


def test_loopback_is_exempt_and_needs_no_token_file(tmp_path):
    for peer in (LOOPBACK, ("::1", 50000), ("::ffff:127.0.0.1", 50000)):
        settings = Settings(root=tmp_path / "registry", stream_port=0)
        assert not settings.token_file.exists()
        with TestClient(create_app(settings), client=peer) as c:
            assert c.post("/sweeps/compile", json=definition()).status_code == 200, peer
            assert c.delete("/levels").status_code == 200, peer


def test_a_missing_token_file_refuses_every_command_from_elsewhere(tmp_path):
    settings = Settings(root=tmp_path / "registry", stream_port=0)
    with TestClient(create_app(settings), client=ELSEWHERE) as c:
        assert c.post("/sweeps/compile", json=definition()).status_code == 401
        assert c.post("/sweeps/compile", json=definition(), headers=bearer("x")).status_code == 401


def test_replay_and_the_read_routes_are_not_commands(tmp_path):
    """Replay is a POST that commands nothing (ADR 0081): open to the network like every read."""
    settings = Settings(root=tmp_path / "registry", stream_port=0)
    with TestClient(create_app(settings), client=ELSEWHERE) as c:
        # 404 (no such record), not 401: the route was reached without a token
        assert c.post("/stream/replay", json={"record_id": NOWHERE}).status_code == 404
        assert c.get("/records").status_code == 200
        assert c.get("/server").json()["read_only"] is False


def test_the_browser_can_see_a_refusal(tmp_path):
    """Flight Deck on another desk: the preflight passes and the 401 carries CORS headers, so the
    browser shows the server's message instead of a CORS error."""
    settings = Settings(root=tmp_path / "registry", stream_port=0)
    with TestClient(create_app(settings), client=ELSEWHERE) as c:
        origin = {"Origin": "http://a-desk:5173"}
        r = c.options(
            "/runs",
            headers={
                **origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert r.status_code == 200
        assert "authorization" in r.headers["access-control-allow-headers"].lower()
        r = c.post("/sweeps/compile", json=definition(), headers=origin)
        assert r.status_code == 401 and r.headers["access-control-allow-origin"] == "*"


def test_the_token_file_format(tmp_path):
    path = tmp_path / "tokens"
    assert read_tokens(path) == {}  # missing: nothing accepted
    first = new_token(path, "  desk   a  ")
    second = new_token(path, "person b")
    assert first != second and len(first) >= 32
    assert read_tokens(path) == {first: "desk a", second: "person b"}
    path.write_text(
        f"# a comment\n\n{first} desk a\n   {second}\nunlabelled-token\n", encoding="utf-8"
    )
    assert read_tokens(path) == {first: "desk a", second: "", "unlabelled-token": ""}
    # appending to a file without a trailing newline does not glue two tokens into one
    path.write_text("abc desk c", encoding="utf-8")
    third = new_token(path, "d")
    assert read_tokens(path) == {"abc": "desk c", third: "d"}


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.1.2.3", True),
        ("::1", True),
        ("::ffff:127.0.0.1", True),
        ("192.0.2.10", False),
        ("::ffff:192.0.2.10", False),
        ("testclient", False),
        ("", False),
    ],
)
def test_is_loopback(host, expected):
    assert is_loopback(host) is expected


def test_the_default_token_file_is_beside_the_registry(tmp_path):
    settings = Settings(root=tmp_path / "registry", stream_port=0)
    assert settings.token_file == tmp_path / "registry" / "tokens"
    assert (
        Settings(root=tmp_path, stream_port=0, tokens=tmp_path / "t").token_file == tmp_path / "t"
    )
