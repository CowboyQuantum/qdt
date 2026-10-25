"""Tutorial 04 — read a measurement from another computer (Step 6c goal 1; ADR 0074, 0080).

A stand server on the measurement PC uploads every record to the registry server on `qdt-db` as soon
as it is ingested. From any other computer there are two ways to read it back:

  A. a Python script through `qdt_registry` with the **reader** DSN — devices, records, results, over
     SQL, but only through the registry's own client (rule 4); it cannot write, and without the payload
     share it reads payload bytes the second way;
  B. **over HTTP** from the read server (`python -m qdt_server --read-only` on `qdt-db`) — the same
     records for any application, plus `GET /records/{id}/payload`: the bytes with their SHA-256. No
     database login, no mounted share.

This file stands the whole chain up in one process so it can run as a test. The registry server is a
SQLite file standing in for Postgres (with `QDT_TEST_PG_DSN` and `QDT_TEST_PG_READER_DSN` set, as in
CI, it is Postgres with a real reader role); the stand server and the read server are the real
applications, driven in-process. On the lab network only three things change: the DSNs name `qdt-db`,
the share is the share, and the servers are services (`deploy/qdt-db/README.md`).
"""

import hashlib
import os
import tempfile
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from qdt_registry import DSN_ENV, STORE_ENV, Registry
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.payload_hdf5 import read_payload
from qdt_server import Settings, create_app
from qdt_sim.scenarios import DEVICE_ID, stability

workdir = Path(tempfile.mkdtemp())

# 1. The registry server: a writer DSN for the stand server, a reader DSN for everyone else, and the
#    payload store (on `qdt-db` a directory exported as a share; here a directory).
share = workdir / "qdt-db" / "payloads"
if os.environ.get("QDT_TEST_PG_DSN") and os.environ.get("QDT_TEST_PG_READER_DSN"):
    WRITER_DSN, READER_DSN = os.environ["QDT_TEST_PG_DSN"], os.environ["QDT_TEST_PG_READER_DSN"]
else:  # SQLite: the same file, opened read-only for the reader
    db = (workdir / "qdt-db" / "registry.sqlite").as_posix()
    share.parent.mkdir(parents=True)
    WRITER_DSN, READER_DSN = f"sqlite:///{db}", f"sqlite:///file:{db}?mode=ro&uri=true"


def poll(condition, timeout=30.0):
    """Wait for something another process (here: another thread) does; True once it has."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if condition():
            return True
        time.sleep(0.1)
    return False


# 2. The measurement PC: a stand server on the simulated stand, configured for the server by the two
#    environment variables (ADR 0080: it syncs after every record, and keeps working when `qdt-db` is
#    unreachable). `python -m qdt_server` reads the same variables; `Settings` is what it builds.
#    The client here speaks from the measurement PC itself (loopback), so its commands need no token;
#    from another computer a stand server wants `Authorization: Bearer <token>` (ADR 0074, 0082).
os.environ[DSN_ENV], os.environ[STORE_ENV] = WRITER_DSN, str(share)
laptop_server = create_app(Settings(root=workdir / "measurement-pc", stream_port=0))
with TestClient(laptop_server, client=("127.0.0.1", 50000)) as laptop:
    run = laptop.post(
        "/runs", json={"definition": stability(8, 12).model_dump(mode="json"), "options": {"seed": 3}}
    ).json()
    assert poll(lambda: laptop.get(f"/runs/{run['run_id']}").json()["state"] == "completed")
    record_id = laptop.get(f"/runs/{run['run_id']}").json()["record_id"]
    local_arrays = Registry(workdir / "measurement-pc").payload(record_id).arrays  # the laptop's own copy

# 3. Read A — a script, from any computer, with the reader DSN and no payload store of its own. The
#    `remote=True` reads ask the server; everything else in the client is its local cache.
script = Registry(workdir / "my-desk", remote_dsn=READER_DSN)
assert poll(lambda: any(r.record_id == record_id for r in script.find(remote=True)))  # synced already
assert DEVICE_ID in [d.device_id for d in script.devices(remote=True)]
record = script.get(record_id, remote=True)
assert record.definition_name == stability(8, 12).name
#    The reader cannot write: a client that tries to sync its own record as the reader is refused.
intruder = Registry(workdir / "intruder", remote_dsn=READER_DSN, remote_store=share)
intruder.register_device(DeviceRecord(device_id="not-mine", kind="double_dot", simulated=True, registered_at=record.started_at))
refused = False
try:
    intruder.sync()
except Exception:  # noqa: BLE001 — "attempt to write a readonly database" / "permission denied for table"
    refused = True
assert refused
assert "not-mine" not in [d.device_id for d in script.devices(remote=True)]
#    And without the share it has no payload bytes: that is what the read server is for.
try:
    script.payload(record_id, remote=True)
    raise AssertionError("a reader without the share has no payload bytes")
except RuntimeError:
    pass

# 4. Read B — over HTTP from the read server on `qdt-db`, which itself reads as the reader role and has
#    the payload store locally. `python -m qdt_server --read-only` is this, as a service.
os.environ[DSN_ENV] = READER_DSN
with TestClient(create_app(Settings(root=workdir / "qdt-db" / "read-server", stream_port=0, read_only=True))) as desktop:
    assert desktop.get("/server").json()["read_only"] is True
    assert record_id in [r["record_id"] for r in desktop.get("/records").json()]
    assert desktop.post("/runs", json={}).status_code in (404, 405)  # no command exists here
    r = desktop.get(f"/records/{record_id}/payload")
    assert r.status_code == 200
    #    Check what arrived against the hash the server sent and the hash the record carries.
    assert hashlib.sha256(r.content).hexdigest() == r.headers["X-Content-SHA256"] == record.payload.sha256
    downloaded = workdir / "my-desk" / "downloaded.h5"
    downloaded.write_bytes(r.content)

# 5. The bytes are the measurement: the same arrays the laptop recorded.
np.testing.assert_array_equal(read_payload(downloaded).arrays["I_sensor"], local_arrays["I_sensor"])

del os.environ[DSN_ENV], os.environ[STORE_ENV]
