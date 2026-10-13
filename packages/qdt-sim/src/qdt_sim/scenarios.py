"""Named, reproducible scenarios: a device, a stand that wires it, and the sweeps that exercise it.

The committed fixture `tests/fixtures/stability_24x32.npy` is `stability_fixture()` run on
`default_device(seed=7)`; `scripts/make_sim_fixtures.py` regenerates it.

A `ScenarioRef` (ADR 0029) names one of `SCENARIOS` plus a seed and scalar parameters; `resolve` turns
it back into the sweep, the stand and the device, so the truth behind a recorded simulation (the model's
`transition_map`) can be regenerated from the ref alone.
"""

from collections.abc import Callable
from typing import NamedTuple

from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition, SymbolBinding
from qdt_schemas.modeling import ScenarioRef
from qdt_schemas.pulse import Measure, PulseSequence, Step, Symbol
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig

from .device import DeviceNoise, SimulatedDevice
from .dot import DoubleDotModel
from .noise import OneOverFNoise, TelegraphNoise, WhiteNoise

DEVICE_ID = "dot"


def default_model() -> DoubleDotModel:
    return DoubleDotModel()


def default_noise(seed: int = 0) -> DeviceNoise:
    """Slow 1/f charge noise on the gates, one dominant trap near the sensor, white readout noise."""
    return DeviceNoise(
        gate=OneOverFNoise(amplitude=150e-6, f_min=1e-2, f_max=1e4, seed=seed),
        sensor=TelegraphNoise(amplitude=4e-3, rate_up=0.5, rate_down=0.5, seed=seed + 1),
        readout=WhiteNoise(sigma=15e-12, seed=seed + 2),
    )


def default_device(
    seed: int = 0, noise: bool = True, stand: StandConfig | None = None, **kwargs
) -> SimulatedDevice:
    """The default device, built from `stand` (default `default_stand()`) by its factory (ADR 0021)."""
    stand = stand or default_stand()
    return SimulatedDevice.from_config(
        stand.instrument(DEVICE_ID),
        stand.instrument_channels(DEVICE_ID),
        default_model(),
        noise=default_noise(seed) if noise else DeviceNoise(),
        seed=seed,
        **kwargs,
    )


def default_stand() -> StandConfig:
    """One instrument, three roles: DC plungers and sensor gate, pulse lines on the plungers, sensor."""
    return StandConfig(
        stand_id="simulated-double-dot",
        instruments=(
            InstrumentConfig(
                id=DEVICE_ID,
                backend="simulated",
                capabilities=("level_source", "level_sense", "sequencer"),
            ),
        ),
        channels=(
            ChannelMap(logical="P1", instrument=DEVICE_ID, channel="P1", quantity="voltage"),
            ChannelMap(logical="P2", instrument=DEVICE_ID, channel="P2", quantity="voltage"),
            ChannelMap(logical="SG", instrument=DEVICE_ID, channel="SG", quantity="voltage"),
            ChannelMap(
                logical="P1_pulse", instrument=DEVICE_ID, channel="P1_pulse", quantity="voltage"
            ),
            ChannelMap(
                logical="P2_pulse", instrument=DEVICE_ID, channel="P2_pulse", quantity="voltage"
            ),
            ChannelMap(
                logical="sensor", instrument=DEVICE_ID, channel="sensor", quantity="current"
            ),
        ),
    )


def read_pixel() -> PulseSequence:
    """Pulse P2 to a level, integrate the sensor."""
    return PulseSequence(
        name="read sensor at a P2 pulse level",
        body=(
            Step(channel="P2_pulse", level=Symbol(name="v_p2", unit="V"), duration=500),
            Measure(channel="sensor", duration=2000, result="I_sensor"),
        ),
    )


def stability(
    n_outer: int = 64,
    n_inner: int = 64,
    *,
    p1: tuple[float, float] = (-0.05, 0.10),
    p2: tuple[float, float] = (-0.05, 0.10),
    shots: int = 1,
    reduce: str | None = None,
    repeats: int | None = 1,
    name: str = "simulated stability diagram",
) -> SweepDefinition:
    """P1 stepped by the DC line, P2 swept by pulses inside the sequencer stage."""
    return SweepDefinition(
        name=name,
        axes=(
            SweepAxis(name="P1", channel="P1", start=p1[0], stop=p1[1], num=n_outer),
            SweepAxis(name="P2", channel="P2_pulse", start=p2[0], stop=p2[1], num=n_inner),
        ),
        stage=SequencerStage(
            instrument=DEVICE_ID,
            axes=("P2",),
            sequence=read_pixel(),
            bindings=(SymbolBinding(symbol="v_p2", axis="P2"),),
            shots=shots,
            reduce={"I_sensor": reduce} if reduce else {},
        ),
        repeats=repeats,
    )


def stability_fixture() -> SweepDefinition:
    """The committed-fixture sweep: small, noisy, 3 shots averaged on the device."""
    return stability(24, 32, shots=3, reduce="mean", name="fixture stability 24x32")


SCENARIOS: dict[str, Callable[..., SweepDefinition]] = {
    "stability": stability,
    "stability_fixture": stability_fixture,
}
"""Sweeps a `ScenarioRef.name` may name. Tuple arguments are passed as `<name>_start` / `<name>_stop`."""

DEVICE_PARAMETERS = {"noise", "sample_charge"}
"""`ScenarioRef.parameters` keys that configure the device rather than the sweep."""


class Scenario(NamedTuple):
    """A resolved `ScenarioRef`: what to run, where, and on which (seeded) device."""

    definition: SweepDefinition
    stand: StandConfig
    device: SimulatedDevice


def resolve(ref: ScenarioRef) -> Scenario:
    """Rebuild the sweep and the seeded device a `ScenarioRef` of kind 'simulation' describes."""
    if ref.kind != "simulation":
        raise ValueError(f"qdt_sim resolves 'simulation' scenarios, not {ref.kind!r}")
    if ref.name not in SCENARIOS:
        raise ValueError(f"unknown scenario {ref.name!r}; have {sorted(SCENARIOS)}")
    params = dict(ref.parameters)
    device_kwargs = {k: params.pop(k) for k in list(params) if k in DEVICE_PARAMETERS}
    ranges: dict[str, dict[str, float]] = {}
    for key in list(params):
        if key.endswith(("_start", "_stop")):
            axis, end = key.rsplit("_", 1)
            ranges.setdefault(axis, {})[end] = float(params.pop(key))
    for axis, ends in ranges.items():
        if set(ends) != {"start", "stop"}:
            raise ValueError(f"scenario parameter {axis!r} needs both _start and _stop")
        params[axis] = (ends["start"], ends["stop"])
    stand = default_stand()
    definition = SCENARIOS[ref.name](**params)
    return Scenario(definition, stand, default_device(seed=ref.seed, stand=stand, **device_kwargs))
