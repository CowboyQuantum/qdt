"""Scenarios: a committed Phantom device (ADR 0087, 0088; `devices/`, written by
`scripts/make_sim_devices.py`, pinned by hash in `DEVICES`), the stand that wires it, the sweeps that
exercise it about its programmed point, and the truth a tune-up must recover."""

import functools
import hashlib
import pathlib

import phantom.api as phantom

from qdt_schemas.activity import SweepDefinition
from qdt_schemas.identity import DeviceLayout
from qdt_schemas.modeling import SimScenario
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig
from qdt_tuning import coulomb_diamonds, stability_diagram

from .device import SENSOR, SimulatedDevice, roles

DEVICE_ID = "dot"
DEFAULT_DEVICE = "two-dot-sige-a"
DEVICES = {
    "two-dot-sige-a": "0ac31718688900366d9da58008da15aae834f08f2880476bf6dbc6975e175903",
    "two-dot-sige-b": "36fb0400267711c4875bbb23a1561edf8c3f23210cae90eb3ead5720a0d91f28",
}
"""Committed device file → its SHA-256 (Phantom 0.2.0). A file that differs is refused."""
LATTICE_SPAN_V = 0.15
"""Half the plunger window of a stability sweep: about six transitions at the devices' ~20 e/V."""
SENSOR_WINDOW_V = (-1.2, 0.8)
"""The sensor-gate window about its programmed level: two peaks of the devices' ~1 V period."""
MEASURE_NS = 1_000_000
"""A stability pixel's integration: Phantom's white floor falls as √(1 ms / dwell)."""
SENSOR_TRUTH = {
    "sg_peak_v": "peak_v",
    "period": "period_v",
    "charging_energy": "charging_energy_ev",
    "lever_arm": "lever_arm_ev_per_v",
    "sg_width_v": "width_v",
    "sg_wing_v": "wing_v",
    "sensitivity_a_per_v": "sensitivity_a_per_v",
}
"""The sensor nodes' output names → Phantom's `SensorTruth` fields."""
LAYOUT_FIELDS = ("material", "channel_nm", "sensor_nm")
"""Phantom's layout fields that `DeviceLayout` takes under the same names."""


@functools.cache
def load_device(name: str = DEFAULT_DEVICE, sha256: str | None = None) -> phantom.Device:
    """The committed device `name`, refused unless its file hashes to `sha256` (default `DEVICES`) and
    the pinned Phantom reads its format."""
    if name not in DEVICES:
        raise ValueError(f"no committed device {name!r}; have {sorted(DEVICES)}")
    text = (pathlib.Path(__file__).parent / "devices" / f"{name}.json").read_bytes()
    got = hashlib.sha256(text).hexdigest()
    if got != (sha256 or DEVICES[name]):
        raise ValueError(f"device file {name!r} hashes to {got}, not {sha256 or DEVICES[name]}")
    return phantom.Device.loads(text.decode("utf-8"))


def programmed(device: phantom.Device | None = None) -> dict[str, float]:
    """The device's programmed point by gate: what a person running it knows (`Device.knowable`)."""
    k = (device or load_device()).knowable()
    return dict(zip(k.gate_names, k.programmed_point_v))


def provenance(name: str = DEFAULT_DEVICE) -> dict[str, str | int]:
    """What made a simulated record (ADR 0087): Phantom's version, its model versions, the file's hash."""
    versions = {f"phantom.{k}": v for k, v in phantom.model_versions().items()}
    attrs = {"phantom_version": phantom.__version__, "device_file": name}
    return attrs | {"device_sha256": DEVICES[name]} | versions


def layout(name: str = DEFAULT_DEVICE) -> DeviceLayout:
    """The device seen from above as `Device.knowable` shows it; each gate on its channel (ADR 0089)."""
    k = load_device(name).knowable().layout
    gates = [
        {f: g[f] for f in ("name", "role", "polygon_nm")} | {"channel": g["name"]}
        for g in k["gates"]
    ]
    source = f"Phantom {phantom.__version__}, device file {name}"
    return DeviceLayout(
        device_id=DEVICE_ID, gates=gates, source=source, **{f: k[f] for f in LAYOUT_FIELDS}
    )


def default_device(
    seed: int | None = 0,
    noise: bool = True,
    stand: StandConfig | None = None,
    device: phantom.Device | None = None,
    **kwargs,
) -> SimulatedDevice:
    """A run on `device` (default `load_device()`) with noise seed `seed`, built from `stand` (default
    `default_stand(device)`) by its factory (ADR 0021)."""
    device = device or load_device()
    stand = stand or default_stand(device)
    instrument, channels = stand.instrument(DEVICE_ID), stand.instrument_channels(DEVICE_ID)
    return SimulatedDevice.from_config(
        instrument, channels, device, noise=noise, seed=seed, **kwargs
    )


def default_stand(device: phantom.Device | None = None) -> StandConfig:
    """One instrument wired to every role of the device (`device.roles`): its gates, the pulse lines
    on the plungers, the sensor's bias (DC and pulse, ADR 0030) and the sensor."""
    capabilities = ("level_source", "level_sense", "sequencer", "triggered_level_source")
    return StandConfig(
        stand_id="simulated-double-dot",
        instruments=(
            InstrumentConfig(id=DEVICE_ID, backend="simulated", capabilities=capabilities),
        ),
        channels=tuple(
            ChannelMap(
                logical=ch,
                instrument=DEVICE_ID,
                channel=ch,
                quantity="current" if role == SENSOR else "voltage",
            )
            for ch, role in roles(device or load_device()).items()
        ),
    )


def about(gate: str, offsets: tuple[float, float]) -> tuple[float, float]:
    """A window `offsets` about the default device's programmed level of `gate`."""
    centre = programmed()[gate]
    return (centre + offsets[0], centre + offsets[1])


def stability(
    n_outer: int = 64,
    n_inner: int = 64,
    *,
    p1: tuple[float, float] | None = None,
    p2: tuple[float, float] = (-LATTICE_SPAN_V, LATTICE_SPAN_V),
    measure_ns: int = MEASURE_NS,
    shots: int = 1,
    reduce: str | None = None,
    repeats: int | None = 1,
    name: str = "simulated stability diagram",
) -> SweepDefinition:
    """`qdt_tuning.stability_diagram` about the programmed point: P1 on its DC line, P2 pulsed about its
    DC level (a pulse adds to it), with `shots` per pixel, their reduction and `repeats`."""
    p1 = p1 or about("P1", (-LATTICE_SPAN_V, LATTICE_SPAN_V))
    d = stability_diagram(
        instrument=DEVICE_ID,
        p1=p1,
        p2=p2,
        n_outer=n_outer,
        n_inner=n_inner,
        measure_ns=measure_ns,
        name=name,
    ).model_dump()
    d["stage"] |= {"shots": shots, "reduce": {"I_sensor": reduce} if reduce else {}}
    return SweepDefinition.model_validate(d | {"repeats": repeats})


def diamonds(
    n_outer: int = 64,
    n_inner: int = 64,
    *,
    sg: tuple[float, float] | None = None,
    bias: tuple[float, float] = (-1.5e-3, 1.5e-3),
    repeats: int | None = 1,
    name: str = "simulated Coulomb diamonds",
) -> SweepDefinition:
    """`qdt_tuning.coulomb_diamonds` (ADR 0030) about the programmed sensor gate: the gate on its DC
    line against the source–drain bias on the `bias` DC line, the sensor current at every point."""
    d = coulomb_diamonds(sg=sg or about("SG", SENSOR_WINDOW_V), bias_v=bias, n=n_outer, name=name)
    d = d.model_dump()
    d["axes"][1]["num"] = n_inner
    return SweepDefinition.model_validate(d | {"repeats": repeats})


def stability_fixture() -> SweepDefinition:
    """The committed-fixture sweep: small, noisy, 3 shots averaged on the device."""
    return stability(24, 32, shots=3, reduce="mean", name="fixture stability 24x32")


# --- scenarios as data (Step 6, ADR 0048, 0088) ----------------------------------------------------


def device_of(scenario: SimScenario) -> phantom.Device:
    return load_device(scenario.device, scenario.device_sha256)


def device_for(scenario: SimScenario, stand: StandConfig | None = None) -> SimulatedDevice:
    """Realize a scenario: a run on its device with its noise seed and noise."""
    return default_device(scenario.seed, scenario.noise, stand, device_of(scenario))


def lattice_truth(
    scenario: SimScenario, x_gate: str = "P1", y_gate: str = "P2"
) -> dict[str, float]:
    """The charge lattice of the scenario's device (Phantom's truth), by the names the `charge-lattice`
    node outputs (`l_ij`, electrons per volt, [dot, gate])."""
    lattice = device_of(scenario).truth((x_gate, y_gate)).charge_lattice_e_per_v
    return {f"l_{i + 1}{j + 1}": float(lattice[i][j]) for i in range(2) for j in range(2)}


def sensor_truth(
    scenario: SimScenario, near_v: float | None = None, bias_v: float | None = None
) -> dict[str, float]:
    """The sensor's Coulomb peak nearest `near_v` (default: the programmed sensor gate) with the other
    gates programmed (Phantom's truth), by the names the `sensor-operating-point` and `sensor-wing`
    nodes output; the sensitivity at source–drain bias `bias_v` (Phantom's default when None)."""
    device = device_of(scenario)
    near_v = programmed(device)["SG"] if near_v is None else near_v
    truth = device.truth(near_v=near_v, v_sd=bias_v).sensor
    return {name: getattr(truth, field) for name, field in SENSOR_TRUTH.items()}
