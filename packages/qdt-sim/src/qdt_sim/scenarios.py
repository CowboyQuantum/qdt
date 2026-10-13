"""Named, reproducible scenarios: a device, a stand that wires it, and the sweeps that exercise it.

The committed fixture `tests/fixtures/stability_24x32.npy` is `stability_fixture()` run on
`default_device(seed=7)`; `scripts/make_sim_fixtures.py` regenerates it.
"""

from qdt_schemas.activity import (
    SensedLevel,
    SequencerStage,
    SweepAxis,
    SweepDefinition,
    SymbolBinding,
)
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
    seed: int = 0,
    noise: bool = True,
    stand: StandConfig | None = None,
    model: DoubleDotModel | None = None,
    **kwargs,
) -> SimulatedDevice:
    """The default device, built from `stand` (default `default_stand()`) by its factory (ADR 0021).
    `model` replaces the default model, e.g. `dataclasses.replace(default_model(), sensor_width_v=0.01)`
    for a colder sensor (ADR 0030)."""
    stand = stand or default_stand()
    return SimulatedDevice.from_config(
        stand.instrument(DEVICE_ID),
        stand.instrument_channels(DEVICE_ID),
        model or default_model(),
        noise=default_noise(seed) if noise else DeviceNoise(),
        seed=seed,
        **kwargs,
    )


def default_stand() -> StandConfig:
    """One instrument, four roles: DC plungers and sensor gate, pulse lines on the plungers, the
    sensor's source–drain bias (DC and pulse, ADR 0030), and the sensor."""
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
            ChannelMap(logical="bias", instrument=DEVICE_ID, channel="bias", quantity="voltage"),
            ChannelMap(
                logical="bias_pulse", instrument=DEVICE_ID, channel="bias_pulse", quantity="voltage"
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


def diamonds(
    n_outer: int = 64,
    n_inner: int = 64,
    *,
    sg: tuple[float, float] = (-0.2, 0.2),
    bias: tuple[float, float] = (-1.5e-3, 1.5e-3),
    repeats: int | None = 1,
    name: str = "simulated Coulomb diamonds",
) -> SweepDefinition:
    """The sensor's Coulomb diamonds (ADR 0030): sensor gate stepped by its DC line, source–drain bias
    stepped by the `bias` DC line, sensor current sensed at every point. Plungers stay at their DC levels."""
    return SweepDefinition(
        name=name,
        axes=(
            SweepAxis(name="SG", channel="SG", start=sg[0], stop=sg[1], num=n_outer),
            SweepAxis(name="V_sd", channel="bias", start=bias[0], stop=bias[1], num=n_inner),
        ),
        sensed=(SensedLevel(name="I_sensor", channel="sensor"),),
        repeats=repeats,
    )


def stability_fixture() -> SweepDefinition:
    """The committed-fixture sweep: small, noisy, 3 shots averaged on the device."""
    return stability(24, 32, shots=3, reduce="mean", name="fixture stability 24x32")
