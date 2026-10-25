"""L1 remote read (Step 6c goal 1, rows R-1 … R-4; ADR 0074, 0080, 0082): the registry on `qdt-db`
read from a computer that is not the measurement PC, and the stand server refusing that computer's
commands without a token. This is the runbook's Part 8 (`deploy/qdt-db/README.md`) as a pytest run, so
the lab PC's deployment is recorded by `scripts/bench_report.py` rather than by hand.

Run it from the other computer (a desk, or `qdt-db` itself for R-1 … R-3) with:

    QDT_READ_SERVER_ADDRESS   the read server, e.g. `http://qdt-db:8700`                      (R-1 … R-3)
    QDT_READER_DSN            the reader role's DSN, `postgresql+psycopg://qdt_reader:…@qdt-db:5432/qdt`
    QDT_STAND_SERVER_ADDRESS  the measurement PC's stand server, e.g. `http://<stand-host>:8700` (R-2, R-4)
    QDT_L1_RECORD_ID          the record to read (default: the newest the read server lists)
    QDT_L1_REMOTE_CONDITION   `normal` (default), `stand-off` (R-2) or `rebooted` (R-3): the state the
                              operator has put the machines in; a row whose condition is not declared skips
    QDT_SCOPE_ADDRESS         optional for R-4: with it, the scope's DC reading is proven unchanged too

A row cannot stop the measurement PC or reboot `qdt-db` itself: R-2 checks that the stand server really
is unreachable before it reads, and R-3 relies on the operator's declaration (Part 8 step 5: restart
`qdt-db` and leave it alone). Addresses and the DSN never reach the report (rule 7; `bench_report.redact`).
"""

import hashlib
import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from qdt_registry import Registry
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.payload_hdf5 import read_payload

PLANNED_BY = ("docs/steps/06c-lab-deployment.md",)
"""The plan that asked for these rows (ADR 0071; `scripts/check_bench_rows.py`)."""

READ_SERVER, STAND_SERVER = "QDT_READ_SERVER_ADDRESS", "QDT_STAND_SERVER_ADDRESS"
READER_DSN, RECORD_ID, CONDITION = "QDT_READER_DSN", "QDT_L1_RECORD_ID", "QDT_L1_REMOTE_CONDITION"
TIMEOUT_S = 30.0
UNREACHABLE_S = 5.0
"""How long a stopped stand server may take to not answer (R-2)."""


def _env(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        pytest.skip(f"{var} not set")
    return value


def _condition() -> str:
    return os.environ.get(CONDITION, "normal").strip().lower()


def _require_condition(name: str, how: str) -> None:
    if _condition() != name:
        pytest.skip(f"{CONDITION}={name} not declared: {how}")


@pytest.fixture
def read_server():
    """The read server on `qdt-db`, as any application sees it: HTTP, no database login."""
    with httpx.Client(base_url=_env(READ_SERVER), timeout=TIMEOUT_S) as client:
        yield client


@pytest.fixture
def reader(tmp_path):
    """A script's view: `qdt_registry` with the reader DSN and an empty cache of its own. The empty
    `remote_store` lets `sync` reach the database (a device needs no payload) so the role's refusal is
    the server's, not the client's."""
    return Registry(
        tmp_path / "desk", remote_dsn=_env(READER_DSN), remote_store=tmp_path / "no-share"
    )


@pytest.fixture
def record_id(read_server) -> str:
    """The record under test: `QDT_L1_RECORD_ID`, or the newest the read server lists (Part 8 step 1
    wrote it from the measurement PC)."""
    if given := os.environ.get(RECORD_ID):
        return given
    listed = [MeasurementRecord.model_validate(r) for r in read_server.get("/records").json()]
    assert listed, (
        "the read server lists no record: run Part 8 step 1 (a sweep on the measurement PC)"
    )
    return max(listed, key=lambda r: r.started_at).record_id


def remote_read(read_server: httpx.Client, reader: Registry, record_id: str, workdir: Path) -> None:
    """R-1's body: the record is listed by the read server, its payload fetched over HTTP with a
    matching SHA-256, and read by a script through `qdt_registry` as the reader, who cannot write."""
    # the read server: a read-only kind, listing the record
    server = read_server.get("/server")
    assert server.status_code == 200 and server.json()["read_only"] is True, server.text
    assert record_id in [r["record_id"] for r in read_server.get("/records").json()]
    record = MeasurementRecord.model_validate(read_server.get(f"/records/{record_id}").json())
    # the payload over HTTP, checked against the hash the server sent and the hash the record carries
    r = read_server.get(f"/records/{record_id}/payload")
    assert r.status_code == 200, r.text
    assert (
        hashlib.sha256(r.content).hexdigest()
        == r.headers["X-Content-SHA256"]
        == record.payload.sha256
    )
    downloaded = workdir / "downloaded.h5"
    downloaded.write_bytes(r.content)
    arrays = read_payload(downloaded).arrays
    assert arrays, "the payload holds no arrays"
    # a script, as the reader role: the same record, through the registry's own client
    assert record_id in [x.record_id for x in reader.find(remote=True)]
    by_script = reader.get(record_id, remote=True)
    assert by_script.payload.sha256 == record.payload.sha256
    assert by_script.definition_name == record.definition_name
    assert record.device_id in [d.device_id for d in reader.devices(remote=True)]
    # the reader cannot write: a sync of its own device is refused by the server
    reader.register_device(
        DeviceRecord(
            device_id="l1-remote-read-reader-probe",
            kind="double_dot",
            simulated=True,
            registered_at=record.started_at,
        )
    )
    with pytest.raises(Exception, match="(?i)permission denied|readonly|read-only"):
        reader.sync()
    assert "l1-remote-read-reader-probe" not in [d.device_id for d in reader.devices(remote=True)]


def test_r1_remote_read(read_server, reader, record_id, tmp_path):
    """R-1: the record is listed, fetched with a matching SHA-256, and read by a script as the reader."""
    remote_read(read_server, reader, record_id, tmp_path)


def test_r2_measurement_pc_off(read_server, reader, record_id, tmp_path):
    """R-2: with the stand server stopped, R-1 passes — everything a reader needs is on `qdt-db`."""
    _require_condition(
        "stand-off", "stop the stand server (or the measurement PC) first, Part 8 step 4"
    )
    stand = _env(STAND_SERVER)
    try:
        answer = httpx.get(f"{stand}/server", timeout=UNREACHABLE_S)
    except httpx.TransportError:
        pass  # refused or timed out: the measurement PC is off, as declared
    else:
        pytest.fail(f"the stand server still answers ({answer.status_code}): stop it before R-2")
    remote_read(read_server, reader, record_id, tmp_path)


def test_r3_after_reboot(read_server, reader, record_id, tmp_path):
    """R-3: `qdt-db` rebooted and left alone, nobody logged in; R-1 passes, so its services start
    on their own (Analysis 0003 §8 step 4; Part 8 step 5). The reboot is the operator's declaration."""
    _require_condition("rebooted", "restart qdt-db, log nobody in, then declare it (Part 8 step 5)")
    remote_read(read_server, reader, record_id, tmp_path)


# --- R-4: commands need a token ----------------------------------------------------------------

COMMANDS = (
    ("POST", "/levels"),
    ("DELETE", "/levels"),
    ("POST", "/sweeps/compile"),
    ("POST", "/runs"),
    ("POST", "/runs/none/abort"),
)
"""Every command a desk can send a stand server. Bodies are deliberately empty: the token check runs
before the body is read, so a refusal is a 401 and a broken check shows as 422, never as a run started."""


def _is_loopback_host(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    try:
        return all(
            ipaddress.ip_address(info[4][0]).is_loopback for info in socket.getaddrinfo(host, None)
        )
    except socket.gaierror:
        return False


def test_r4_commands_need_a_token(request):
    """R-4: a command to the stand server from this computer without a token is refused, and changes
    nothing: the held levels, the run list and (with a scope cabled) the scope's reading are the same
    before and after. A wrong token is refused too."""
    stand = _env(STAND_SERVER)
    if _is_loopback_host(stand):
        pytest.skip(f"{STAND_SERVER} is this computer: R-4 is run from another computer (ADR 0082)")
    scope = request.getfixturevalue("scope") if os.environ.get("QDT_SCOPE_ADDRESS") else None
    read_scope = _scope_reader(scope)
    with httpx.Client(base_url=stand, timeout=TIMEOUT_S) as c:
        server = c.get("/server")
        assert server.status_code == 200 and server.json()["read_only"] is False, server.text
        before = (
            c.get("/levels").json(),
            {r["run_id"] for r in c.get("/runs").json()},
            read_scope(),
        )
        for method, path in COMMANDS:
            r = c.request(method, path)
            assert r.status_code == 401, (
                f"{method} {path} without a token: {r.status_code} {r.text}"
            )
            assert r.headers.get("www-authenticate") == "Bearer"
            assert "Authorization: Bearer" in r.json()["detail"]
            r = c.request(method, path, headers={"Authorization": "Bearer not-in-the-file"})
            assert r.status_code == 401, (
                f"{method} {path} with a wrong token: {r.status_code} {r.text}"
            )
            assert r.headers.get("www-authenticate", "").startswith("Bearer")
        # reads stay open to the network
        assert c.get("/stand").status_code == 200
        after = (
            c.get("/levels").json(),
            {r["run_id"] for r in c.get("/runs").json()},
            read_scope(),
        )
    assert after[0] == before[0], "the held levels changed"
    assert after[1] == before[1], "a run appeared or disappeared"
    if scope is not None:
        from scope_accuracy import dc_measurement_tolerance
        from test_l1_loopback import SCOPE_CHANNEL

        tol = dc_measurement_tolerance(SCOPE_CHANNEL)
        assert abs(after[2] - before[2]) <= tol, (
            f"scope ch{SCOPE_CHANNEL.number} read {before[2]:+.4f} V before and {after[2]:+.4f} V "
            f"after the refused commands (tolerance ±{tol:.4f} V)"
        )


def _scope_reader(scope):
    """The scope's DC reading on the L1 channel, through the `WaveformSense` protocol; a no-op without
    a scope (the levels and the run list are then the only witnesses)."""
    if scope is None:
        return lambda: None
    from test_l1_loopback import SCOPE_CHANNEL, read_dc

    return lambda: read_dc(scope, f"ch{SCOPE_CHANNEL.number}")
