"""The VISA transport discards an instrument's unread output before every query (bench 2026-10-19:
a failed query's reply, read by the next one, shifted a QDAC-II's replies by one)."""

import numpy as np

from qdt_lab.drivers.scpi import _VisaTransport


class _Resource:
    def __init__(self, flush_raises: Exception | None = None) -> None:
        self.calls: list[tuple] = []
        self.flush_raises = flush_raises

    def flush(self, mask):
        self.calls.append(("flush", mask))
        if self.flush_raises:
            raise self.flush_raises

    def write(self, command):
        self.calls.append(("write", command))

    def query(self, command):
        self.calls.append(("query", command))
        return " reply \n"

    def query_binary_values(self, command, datatype, is_big_endian, container):
        self.calls.append(("block", command))
        return container([1, 2], dtype=np.int16)

    def close(self):
        self.calls.append(("close",))


def test_a_query_discards_pending_input_first_and_a_write_does_not():
    from pyvisa import constants

    r = _Resource()
    t = _VisaTransport(r)
    t.write("*RST")
    assert t.query("*IDN?") == "reply"
    assert t.query_block(":WAVeform:DATA?", "<i2").tolist() == [1, 2]
    assert r.calls == [
        ("write", "*RST"),
        ("flush", constants.VI_READ_BUF_DISCARD),
        ("query", "*IDN?"),
        ("flush", constants.VI_READ_BUF_DISCARD),
        ("block", ":WAVeform:DATA?"),
    ]


def test_a_session_that_cannot_discard_still_answers():
    r = _Resource(flush_raises=NotImplementedError("no flush on this session"))
    assert _VisaTransport(r).query("*IDN?") == "reply"
    assert ("query", "*IDN?") in r.calls
