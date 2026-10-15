"""`SweepDefinition` + `StandConfig` → `ExecutionPlan` (ADR 0019; captures by ADR 0047).

Dataset layout, outer to inner: `repeat` (when repeats != 1), the axes, `shot` (kept shots), then for
captured waveforms `record` (when records > 1) and each capture's time axis. A sensed level is laid over
the stepped axes; a stage result over every axis; a capture over the stepped axes plus its own time.
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from qdt_schemas.activity import (
    ExecutionPlan,
    ParameterBinding,
    ResolvedChannel,
    SequencerProgram,
    SweepDefinition,
)
from qdt_schemas.data import (
    Dataset,
    DataVariable,
    Dimension,
    LinearCoordinate,
    SourceDescriptor,
)
from qdt_schemas.stand import QUANTITY_UNIT, Capability, StandConfig

from .emit import Emitter

REPEAT_DIM = "repeat"
SHOT_DIM = "shot"
RECORD_DIM = "record"


def compile_sweep(
    definition: SweepDefinition,
    stand: StandConfig,
    emitters: Mapping[str, Emitter] = (),
    *,
    plan_id: str | None = None,
    created_at: datetime | None = None,
) -> ExecutionPlan:
    """Resolve channels and capabilities, emit the stage program, declare the Dataset.

    Raises ValueError for a channel used in two roles, a missing capability, or an unbound parameter.
    """
    roles: dict[str, Capability] = {}

    def resolve(logical: str, role: Capability) -> None:
        if logical in roles and roles[logical] != role:
            raise ValueError(
                f"channel {logical!r} is used as {roles[logical]} and {role}: one terminal, one role"
            )
        roles[logical] = role
        instrument = stand.instrument(stand.channel(logical).instrument)
        if role not in instrument.capabilities:
            raise ValueError(
                f"instrument {instrument.id!r} ({logical!r}) lacks capability {role!r}"
            )

    stepped = definition.stepped_axes()
    for a in stepped:
        resolve(a.channel, "level_source")
    for lv in definition.levels:  # the operating point (ADR 0038)
        resolve(lv.channel, "level_source")
    for s in definition.sensed:
        resolve(s.channel, "level_sense")
    for c in definition.captured:  # time-resolved records (ADR 0047)
        resolve(c.channel, "waveform_sense")

    program: SequencerProgram | None = None
    bindings: tuple[ParameterBinding, ...] = ()
    stage = definition.stage
    if stage is not None:
        instrument = stand.instrument(stage.instrument)
        if "sequencer" not in instrument.capabilities:
            raise ValueError(f"instrument {stage.instrument!r} is not a sequencer")
        for a in definition.stage_axes():
            if stand.channel(a.channel).instrument != stage.instrument:
                raise ValueError(
                    f"stage axis {a.name!r} is on {a.channel!r}, not a channel of {stage.instrument!r}"
                )
            resolve(a.channel, "sequencer")
        if stage.sequence is not None:
            for ch in stage.sequence.channels():
                if stand.channel(ch).instrument != stage.instrument:
                    raise ValueError(
                        f"sequence channel {ch!r} is not a channel of {stage.instrument!r}"
                    )
                resolve(ch, "sequencer")
            emitter = dict(emitters).get(instrument.backend)
            if emitter is None:
                raise ValueError(f"no emitter for backend {instrument.backend!r}")
            program, bindings = emitter.emit(
                stage,
                {a.name: a for a in definition.axes},
                {ch: stand.channel(ch) for ch in stage.sequence.channels()},
            )
        else:
            program, bindings = stage.program, stage.parameters
        for b in bindings:
            if b.source != "const" and b.axis not in {a.name for a in definition.axes}:
                raise ValueError(f"parameter {b.parameter!r} names unknown axis {b.axis!r}")
            if b.source == "axis_value" and b.axis in stage.axes:
                raise ValueError(
                    f"parameter {b.parameter!r}: axis_value needs a stepped axis, {b.axis!r} is a stage axis"
                )

    channels = tuple(
        ResolvedChannel(
            logical=logical,
            instrument=stand.channel(logical).instrument,
            channel=stand.channel(logical).channel,
            quantity=stand.channel(logical).quantity,
            settle_s=stand.channel(logical).settle_s,
            integration_s=stand.channel(logical).integration_s,
            role=role,
        )
        for logical, role in roles.items()
    )

    plan_id = plan_id or uuid.uuid4().hex
    dataset = _declare_dataset(definition, stand, program, plan_id, created_at)
    return ExecutionPlan(
        plan_id=plan_id,
        definition=definition,
        stand_id=stand.stand_id,
        dataset=dataset,
        channels=channels,
        stage_program=program,
        stage_parameters=bindings,
    )


def _declare_dataset(
    definition: SweepDefinition,
    stand: StandConfig,
    program: SequencerProgram | None,
    plan_id: str,
    created_at: datetime | None,
) -> Dataset:
    dims: list[Dimension] = []
    coords: list[LinearCoordinate] = []
    outer: list[str] = []
    if definition.repeats != 1:
        dims.append(Dimension(name=REPEAT_DIM, size=definition.repeats))
        outer.append(REPEAT_DIM)
    for a in definition.axes:
        dims.append(Dimension(name=a.name, size=a.num))
        coords.append(
            LinearCoordinate(
                name=a.name,
                dim=a.name,
                unit=QUANTITY_UNIT[stand.channel(a.channel).quantity],
                start=a.start,
                stop=a.stop,
                num=a.num,
            )
        )
    stepped_names = [a.name for a in definition.stepped_axes()]
    variables: list[DataVariable] = []
    attrs: dict = {"definition": definition.name, "repeats": definition.repeats or "unbounded"}
    for s in definition.sensed:
        variables.append(
            DataVariable(
                name=s.name,
                dims=(*outer, *stepped_names),
                unit=QUANTITY_UNIT[stand.channel(s.channel).quantity],
                dtype="float64",
            )
        )
    stage = definition.stage
    if stage is not None and program is not None:
        attrs["shots"] = stage.shots
        keep_shots = stage.shots > 1 and any(
            stage.reduction(r.name) == "keep" for r in program.results
        )
        if keep_shots:
            dims.append(Dimension(name=SHOT_DIM, size=stage.shots))
        for r in program.results:
            reduction = stage.reduction(r.name)
            vdims = (*outer, *(a.name for a in definition.axes))
            if stage.shots > 1 and reduction == "keep":
                vdims = (*vdims, SHOT_DIM)
            else:
                attrs[f"{r.name}.reduced"] = f"shot:{reduction}" if stage.shots > 1 else "none"
            variables.append(DataVariable(name=r.name, dims=vdims, unit=r.unit, dtype=r.dtype))
    captured = definition.captured
    if captured:
        records = captured[0].records  # the schema holds every capture to one count
        if records > 1:
            dims.append(Dimension(name=RECORD_DIM, size=records))
        declared: set[str] = set()
        for c in captured:
            tdim = definition.capture_time_dim(c.name)
            if tdim not in declared:
                dims.append(Dimension(name=tdim, size=c.num))
                coords.append(
                    LinearCoordinate(
                        name=tdim, dim=tdim, unit="s", start=c.start_s, stop=c.stop_s, num=c.num
                    )
                )
                declared.add(tdim)
            variables.append(
                DataVariable(
                    name=c.name,
                    dims=(*outer, *stepped_names, *((RECORD_DIM,) if records > 1 else ()), tdim),
                    unit=QUANTITY_UNIT[stand.channel(c.channel).quantity],
                    dtype="float64",
                )
            )
        attrs["records"] = records
    simulated = all(i.backend == "simulated" for i in stand.instruments)
    return Dataset(
        dataset_id=plan_id,
        name=definition.name,
        dims=tuple(dims),
        coords=tuple(coords),
        data_vars=tuple(variables),
        attrs=attrs | dict(definition.attrs),
        source=SourceDescriptor(kind="simulation" if simulated else "live", label=definition.name),
        created_at=created_at or datetime.now(UTC),
    )
