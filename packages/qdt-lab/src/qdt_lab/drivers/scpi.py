"""SCPI transport shared by the instrument drivers (Step 5).

A driver talks to its instrument only through `ScpiTransport`: text commands, text queries, and
IEEE 488.2 definite-length binary blocks. `open_visa` builds one over pyvisa (an optional extra,
imported lazily, ADR 0006). Tests hand a driver an emulator implementing the same three calls, so the
conformance suite runs on the real driver code without hardware.
"""

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class ScpiTransport(Protocol):
    """Line-oriented SCPI over any link (TCP socket, USB, GPIB, an emulator)."""

    def write(self, command: str) -> None:
        """Send one command; no response is read."""
        ...

    def query(self, command: str) -> str:
        """Send one query and return its response line, stripped."""
        ...

    def query_block(self, command: str, dtype: str) -> np.ndarray:
        """Send a query answered by an IEEE 488.2 definite-length block of `dtype` values
        (numpy dtype string with byte order, e.g. '<i2'); return them as a 1-D array."""
        ...

    def close(self) -> None:
        """Release the link; idempotent."""
        ...


def parse_block(raw: bytes) -> bytes:
    """The payload of an IEEE 488.2 definite-length block `#<n><len><payload>[\\n]`."""
    if not raw.startswith(b"#") or len(raw) < 2 or not raw[1:2].isdigit():
        raise ValueError(f"not an IEEE 488.2 definite-length block: {raw[:12]!r}")
    n = int(raw[1:2])
    if n == 0:
        raise ValueError("indefinite-length blocks (#0) are not supported")
    length = int(raw[2 : 2 + n])
    payload = raw[2 + n : 2 + n + length]
    if len(payload) != length:
        raise ValueError(f"block truncated: {len(payload)} of {length} bytes")
    return payload


def make_block(payload: bytes) -> bytes:
    """Wrap `payload` as an IEEE 488.2 definite-length block (for emulators)."""
    length = str(len(payload)).encode()
    return b"#" + str(len(length)).encode() + length + payload


class _VisaTransport:
    def __init__(self, resource) -> None:
        self._r = resource

    def write(self, command: str) -> None:
        self._r.write(command)

    def query(self, command: str) -> str:
        return self._r.query(command).strip()

    def query_block(self, command: str, dtype: str) -> np.ndarray:
        dt = np.dtype(dtype)
        return np.asarray(
            self._r.query_binary_values(
                command,
                datatype=dt.char,
                is_big_endian=dt.byteorder == ">",
                container=np.array,
            ),
            dtype=dt,
        )

    def close(self) -> None:
        if self._r is not None:
            self._r.close()
            self._r = None


def open_visa(
    address: str,
    *,
    timeout_s: float = 10.0,
    termination: str = "\n",
    baud_rate: int | None = None,
) -> ScpiTransport:
    """Open `address` (a VISA resource string, e.g. 'TCPIP::<host>::5025::SOCKET' or
    'ASRL/dev/cu.usbserial-NNNN::INSTR') with pyvisa, using the pure-Python backend when no vendor
    VISA library is installed. `baud_rate` applies to serial resources only (pyserial needed)."""
    try:
        import pyvisa
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError("install the instrument extra, e.g. `qdt-lab[qdac]`, for pyvisa") from e
    try:
        rm = pyvisa.ResourceManager()
    except (OSError, ValueError):
        rm = pyvisa.ResourceManager("@py")
    resource = rm.open_resource(address)
    if baud_rate is not None and hasattr(resource, "baud_rate"):
        resource.baud_rate = int(baud_rate)
    resource.timeout = int(timeout_s * 1000)
    resource.read_termination = termination
    resource.write_termination = termination
    return _VisaTransport(resource)


def channel_number(channel: str, lo: int, hi: int) -> int:
    """The instrument channel number in a vendor channel id ('3', 'ch03', 'CHAN3', 'out3'); ValueError
    unless it lies in [lo, hi]."""
    digits = "".join(c for c in channel if c.isdigit())
    if not digits:
        raise ValueError(f"channel {channel!r} names no channel number")
    n = int(digits)
    if not lo <= n <= hi:
        raise ValueError(f"channel {channel!r} is outside {lo}..{hi}")
    return n
