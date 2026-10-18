"""`SweepDefinition` + `StandConfig` → `ExecutionPlan` (ADR 0019; captures by ADR 0047 and 0060).

The definition says what is swept; the plan says how each axis advances (ADR 0066): `resolve_pacing`
decides, from the stand, whether a stepped axis is set by the executor or triggered by the stage's
sequencer, and the plan and the Dataset's attrs (`<axis>.pacing`) record it.

Dataset layout, outer to inner: `repeat` (when repeats != 1), the axes, `shot` (kept shots), then for
captured waveforms `record` (when records > 1) and each capture's time axis. A sensed level is laid over
the stepped axes; a stage result over every axis; a capture over the stepped axes plus its own time; a
shot capture (ADR 0060) over the stepped axes, `shot` when shots are kept, and its own time from 0.
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from qdt_schemas.activity import (
    AxisPacing,
    ExecutionPlan,
    ParameterBinding,
    ResolvedChannel,
    SequencerProgram,
    SweepAxis,
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

from .emit import Emitter, TriggeredStep, once_results

REPEAT_DIM = "repeat"
SHOT_DIM = "shot"
RECORD_DIM = "record"


def resolve_pacing(definition: SweepDefinition, stand: StandConfig) -> tuple[AxisPacing, ...]:
    """How each axis of `definition` advances on `stand`, in axis order (ADR 0066).

    A stage axis is swept by the sequencer. The innermost stepped axis is triggered when its
    preference allows it ('auto' or 'triggered') and the sweep and the stand can honour it: a
    sequenced stage plays the markers, nothing is sensed or captured per point, and the axis's channel
    and every coupled companion sit on instruments that step a list on a trigger and are wired to the
    stage's sequencer (`settings['trigger_from']`, or the sequencer itself). Every other stepped axis
    is set by the executor. Raises ValueError for a forced 'triggered' the stand cannot honour, and
    for a `trigger_from` that names no channel of the sequencer (a stand file error, never a fallback).
    """
    stage_axes = set(definition.stage.axes) if definition.stage else set()
    out = {
        a.name: AxisPacing(axis=a.name, pacing="sequencer" if a.name in stage_axes else "software")
        for a in definition.axes
    }
    stepped = definition.stepped_axes()
    if stepped and stepped[-1].stepping != "software":
        last = stepped[-1]
        lines, why = _trigger_lines(definition, stand, last)
        if lines is not None:
            out[last.name] = AxisPacing(axis=last.name, pacing="triggered", lines=lines)
        elif last.stepping == "triggered":
            raise ValueError(f"axis {last.name!r} is set to 'triggered', but {why}")
    # a forced trigger on any other axis is refused by the definition itself
    return tuple(out[a.name] for a in definition.axes)


def _trigger_lines(
    definition: SweepDefinition, stand: StandConfig, axis: SweepAxis
) -> tuple[tuple[str, ...] | None, str]:
    """The marker lines that advance `axis`, or None and why it cannot be triggered here."""
    stage = definition.stage
    if stage is None or stage.sequence is None:
        return None, "the sweep has no sequenced stage to play its trigger"
    if definition.sensed or definition.captured:
        return (
            None,
            "the sweep senses or captures per point, which needs the executor at every point",
        )
    lines: list[str] = []
    for ch in (axis.channel, *axis.couplings):
        instrument = stand.instrument(stand.channel(ch).instrument)
        if "triggered_level_source" not in instrument.capabilities:
            return None, f"instrument {instrument.id!r} ({ch!r}) cannot step a list on a trigger"
        if instrument.id == stage.instrument:
            continue  # the sequencer sets the level itself (the simulated device)
        line = instrument.settings.get("trigger_from")
        if line is None:
            return None, (
                f"instrument {instrument.id!r} ({ch!r}) has no settings['trigger_from'], the "
                "sequencer channel wired to its trigger input"
            )
        line = str(line)
        if line not in {c.logical for c in stand.channels} or (
            stand.channel(line).instrument != stage.instrument
        ):
            raise ValueError(
                f"instrument {instrument.id!r} says settings['trigger_from'] = {line!r}, which is "
                f"not a channel of the sequencer {stage.instrument!r}"
            )
        if line not in lines:
            lines.append(line)
    return tuple(lines), ""


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
            # a TriggeredLevelSource is a LevelSource: a held level on a channel the triggered axis
            # moves as a companion (the coupling's origin, ADR 0049) keeps the one terminal, one role
            levels = {"level_source", "triggered_level_source"}
            if {roles[logical], role} != levels:
                raise ValueError(
                    f"channel {logical!r} is used as {roles[logical]} and {role}: one terminal, one role"
                )
            role = "triggered_level_source"
        roles[logical] = role
        instrument = stand.instrument(stand.channel(logical).instrument)
        if role not in instrument.capabilities:
            raise ValueError(
                f"instrument {instrument.id!r} ({logical!r}) lacks capability {role!r}"
            )

    pacing = resolve_pacing(definition, stand)
    triggered = next((definition.axis(p.axis) for p in pacing if p.pacing == "triggered"), None)
    stepped = definition.stepped_axes()
    for a in stepped:
        # a triggered axis (ADR 0064) and its companions are loaded as lists, not set per point
        role: Capability = "triggered_level_source" if a is triggered else "level_source"
        resolve(a.channel, role)
        for ch in a.couplings:  # a virtual gate's companions (ADR 0049)
            resolve(ch, role)
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
            # a shot capture's scope (ADR 0060) is armed by the executor and triggered by the shot: its
            # channel is a WaveformSense of another instrument, never a sequencer channel
            for c in stage.captures():
                if stand.channel(c.channel).instrument == stage.instrument:
                    raise ValueError(
                        f"capture {c.result!r} is on the sequencer's own input {c.channel!r}; a capture "
                        "on the sequencer is not emitted yet (ADR 0060): put the scope on its own instrument"
                    )
                resolve(c.channel, "waveform_sense")
            scope_channels = {c.channel for c in stage.captures()}
            for ch in stage.sequence.channels():
                if ch in scope_channels:
                    continue
                if stand.channel(ch).instrument != stage.instrument:
                    raise ValueError(
                        f"sequence channel {ch!r} is not a channel of {stage.instrument!r}"
                    )
                resolve(ch, "sequencer")
            emitter = dict(emitters).get(instrument.backend)
            if emitter is None:
                raise ValueError(f"no emitter for backend {instrument.backend!r}")

            def marker_line(stepped_instrument: str, what: str) -> str | None:
                """The logical sequencer channel whose marker drives `stepped_instrument`'s trigger
                input: its `settings['trigger_from']`. None when it is the sequencer itself (it
                triggers itself) or, for a scope, when it has none (it triggers itself, ADR 0063)."""
                if stepped_instrument == stage.instrument:
                    return None
                line = stand.instrument(stepped_instrument).settings.get("trigger_from")
                if line is None:
                    return None
                line = str(line)
                if line not in {c.logical for c in stand.channels} or (
                    stand.channel(line).instrument != stage.instrument
                ):
                    raise ValueError(
                        f"{what}: instrument {stepped_instrument!r} says settings['trigger_from'] = "
                        f"{line!r}, which is not a channel of the sequencer {stage.instrument!r}"
                    )
                resolve(line, "sequencer")
                return line

            trigger_step = None
            if triggered is not None:  # resolved above (ADR 0066); its lines are sequencer channels
                lines = next(p.lines for p in pacing if p.axis == triggered.name)
                for line in lines:
                    resolve(line, "sequencer")
                settle = max(
                    stand.channel(ch).settle_s for ch in (triggered.channel, *triggered.couplings)
                )
                trigger_step = TriggeredStep(
                    axis=triggered.name, lines=lines, settle_ns=round(settle * 1e9)
                )
            # ADR 0068: a stage with no axis of its own records once per run, laid at the stepped point;
            # with no axis anywhere and no repeats that value would be a Dataset with no dimension
            single = once_results(stage, (*((triggered.name,) if triggered else ()), *stage.axes))
            if single and not definition.axes and definition.repeats == 1:
                raise ValueError(
                    f"result {single[0]!r} would be one number with no axis: give the sweep an axis, "
                    "keep shots > 1, or repeat it"
                )
            capture_lines = {}
            for c in stage.captures():
                line = marker_line(stand.channel(c.channel).instrument, f"capture {c.result!r}")
                if line is not None:
                    capture_lines[c.channel] = line
            program, bindings = emitter.emit(
                stage,
                {a.name: a for a in definition.axes},
                {ch: stand.channel(ch) for ch in stage.sequence.channels()},
                triggered=trigger_step,
                lines=capture_lines,
            )
            if not program.results and stage.shots > 1 and not stage.captures():
                raise ValueError("a stage with no results and no capture records nothing")
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
    dataset = _declare_dataset(definition, stand, program, plan_id, created_at, pacing)
    return ExecutionPlan(
        plan_id=plan_id,
        definition=definition,
        stand_id=stand.stand_id,
        dataset=dataset,
        channels=channels,
        stage_program=program,
        stage_parameters=bindings,
        pacing=pacing,
    )


def _declare_dataset(
    definition: SweepDefinition,
    stand: StandConfig,
    program: SequencerProgram | None,
    plan_id: str,
    created_at: datetime | None,
    pacing: tuple[AxisPacing, ...] = (),
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
    for p in pacing:  # how each axis was taken: the record says it (ADR 0066)
        attrs[f"{p.axis}.pacing"] = p.pacing
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
    if stage is not None and stage.captures():
        # ADR 0060: one record per shot on a time axis from the capture's point in the shot
        keep = stage.shots > 1
        if keep and SHOT_DIM not in {d.name for d in dims}:
            dims.append(Dimension(name=SHOT_DIM, size=stage.shots))
        for c in stage.captures():
            tdim = definition.capture_time_dim(c.result)
            if tdim not in {d.name for d in dims}:
                dims.append(Dimension(name=tdim, size=c.num))
                coords.append(
                    LinearCoordinate(
                        name=tdim, dim=tdim, unit="s", start=0.0, stop=c.duration_s, num=c.num
                    )
                )
            variables.append(
                DataVariable(
                    name=c.result,
                    dims=(*outer, *stepped_names, *((SHOT_DIM,) if keep else ()), tdim),
                    unit=QUANTITY_UNIT[stand.channel(c.channel).quantity],
                    dtype="float64",
                )
            )
        attrs["shots"] = stage.shots
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
