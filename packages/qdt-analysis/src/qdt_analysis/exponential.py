"""A single exponential on a 1-D trace: `y(t) = offset + amplitude · exp(−(t − t_start) / tau)`.

The L2-3 oracle (BENCH.md, ADR 0040): a step from a pulse source into a passive network, read by a
`WaveformSense` on the declared time grid. After the edge the output relaxes exponentially: a bias tee's
droop decays to zero with the low-frequency time constant of its datasheet, a low-pass approaches the
step's plateau (Probe 03's combiner, τ = 7.9 ms). The same model covers both: `amplitude` is positive
for a decay and negative for an approach, `offset` is the asymptote.

1. **Trace**: the variable's last dim is time, on a `LinearCoordinate`; any leading dims (record, shot)
   carry no coordinate and are averaged over, ignoring NaN. A variable with a coordinate on a leading
   dim is a map, not a trace, and is refused.
2. **Edge**: the slope of the box-smoothed trace (width `n // 100` samples, at least one) is taken, and
   the edge is the centre of the strongest part (within a tenth of its peak) of the *first* run where
   its magnitude reaches half the maximum. The first run, not the global maximum, so a pulse's rising
   edge wins over its falling one; the centre of the strongest part, so a sharp edge smoothed into a
   ramp is placed at the edge and a slow onset late rather than early (points before the edge are the
   ones that break the model).
3. **Window**: from the first sample after the edge, plus `skip`, for `span` (0: to the end of the
   record). `t_start` is the first sample in the window; `amplitude` is the exponential term there.
4. **Fit** by nonlinear least squares (`scipy.optimize.curve_fit`) from a log-linear starting point,
   with standard errors from the residual variance (`N − 3` degrees of freedom).
5. **Judge**: fewer than four points, a constant window, a fit that does not converge, or an
   exponential explaining less than `min_r2` of the window's variance is `failed`.

Estimates: `tau`, `amplitude`, `offset` (with standard errors), `residual_rms` and `r2`. Overlays are
two `marker` annotations on the time coordinate, the edge (`t_start`) and `t_start + tau`; a curve
through the data needs the value axis, which is not a coordinate, so the fitted curve and the residual
over the record's time coordinate are the output payload instead (ADR 0031, 0046). Pure (rule 5).
"""

import math
import uuid
import warnings
from datetime import UTC, datetime
from typing import NamedTuple

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.optimize import OptimizeWarning, curve_fit

from qdt_schemas.data import (
    Annotation,
    Coordinate,
    Dataset,
    DataVariable,
    Dimension,
    LinearCoordinate,
    SourceDescriptor,
)
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.modeling import AnalysisResult, Estimate, FitModel
from qdt_schemas.payload_hdf5 import Payload

from .transitions import Analysis

NAME = "qdt_analysis.exponential.fit_exponential"
VERSION = "1"


class Exponential(NamedTuple):
    """The least-squares exponential `offset + amplitude · exp(−(t − t_start) / tau)` and its figures
    of merit."""

    tau: float
    amplitude: float
    offset: float
    t_start: float
    stderr: tuple[float, float, float]
    """Standard errors of (tau, amplitude, offset); NaN where the covariance is not finite."""
    r2: float
    """Fraction of the window's variance the exponential explains."""
    residual_rms: float
    n_points: int

    def at(self, t: np.ndarray) -> np.ndarray:
        return _model(t, self.tau, self.amplitude, self.offset, self.t_start)


def _model(t, tau, amplitude, offset, t_start):
    return offset + amplitude * np.exp(-(t - t_start) / tau)


def detect_edge(y: np.ndarray) -> int:
    """Index of the edge in the trace `y`: the centre of the strongest part of the first run where the
    magnitude of the smoothed slope reaches half its maximum. Raises ValueError for a trace with fewer
    than two finite points or no slope at all."""
    finite = np.isfinite(y)
    if finite.sum() < 2:
        raise ValueError("a trace needs at least two finite points")
    filled = np.interp(np.arange(y.size), np.flatnonzero(finite), y[finite])
    width = max(1, y.size // 100)
    smooth = uniform_filter1d(filled, width, mode="nearest") if width > 1 else filled
    slope = np.abs(np.gradient(smooth))
    peak = slope.max()
    if not peak > 0:
        raise ValueError("the trace has no slope")
    above = slope >= 0.5 * peak
    first = int(np.argmax(above))
    after = np.flatnonzero(~above[first:])
    stop = first + int(after[0]) if after.size else y.size
    run = slope[first:stop]
    # a sharp edge smoothed over `width` samples is a plateau of equal slopes: its centre is the edge
    top = np.flatnonzero(run >= 0.9 * run.max())
    return first + int(top[0] + top[-1]) // 2


def fit(t: np.ndarray, y: np.ndarray) -> Exponential:
    """Nonlinear least squares of `offset + amplitude · exp(−(t − t[0]) / tau)` to the finite points of
    `y` over `t`. Raises ValueError with fewer than four finite points, a constant `y`, or a fit that
    does not converge."""
    keep = np.isfinite(y)
    n = int(keep.sum())
    if n < 4:
        raise ValueError(f"only {n} finite point(s); an exponential needs four")
    tt, yy = t[keep], y[keep]
    t_start = float(t[0])
    tss = float(((yy - yy.mean()) ** 2).sum())
    if tss == 0.0:
        raise ValueError("the window is constant")
    # starting point: the asymptote from the last tenth, the rate from a log-linear fit of the rest
    tail = max(1, n // 10)
    offset0 = float(yy[-tail:].mean())
    amplitude0 = float(yy[0] - offset0)
    if amplitude0 == 0.0:
        amplitude0 = float(yy[: max(1, n // 10)].mean() - offset0) or tss**0.5
    excess = (yy - offset0) / amplitude0
    usable = excess > 0.05
    tau0 = (tt[-1] - tt[0]) / 3
    if usable.sum() >= 2:
        k, _ = np.polyfit(tt[usable] - t_start, np.log(excess[usable]), 1)
        if k < 0 and math.isfinite(k):
            tau0 = -1 / k
    tau0 = min(max(float(tau0), (tt[-1] - tt[0]) / n), 10 * (tt[-1] - tt[0]))
    try:
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", OptimizeWarning)  # a non-finite covariance: stderr None
            coefficients, covariance = curve_fit(
                lambda x, tau, a, c: _model(x, tau, a, c, t_start),
                tt,
                yy,
                p0=(tau0, amplitude0, offset0),
                bounds=([1e-300, -np.inf, -np.inf], [np.inf, np.inf, np.inf]),
                maxfev=20000,
            )
    except (RuntimeError, ValueError) as e:
        raise ValueError(f"the fit did not converge: {e}") from None
    tau, amplitude, offset = (float(v) for v in coefficients)
    residual = yy - _model(tt, tau, amplitude, offset, t_start)
    rss = float(residual @ residual)
    with np.errstate(all="ignore"):
        stderr = tuple(float(v) for v in np.sqrt(np.diag(covariance)))
    return Exponential(
        tau,
        amplitude,
        offset,
        t_start,
        stderr,
        1.0 - rss / tss,
        math.sqrt(rss / n),
        n,
    )


def _pick_trace(payload: Payload, variable: str) -> tuple[DataVariable, LinearCoordinate]:
    """(variable, time coordinate): the first data variable whose last dim carries a linear
    coordinate and whose leading dims carry none."""
    dataset = payload.dataset
    coords: dict[str, Coordinate] = {c.dim: c for c in dataset.coords}
    candidates = [v for v in dataset.data_vars if not variable or v.name == variable]
    if not candidates:
        raise ValueError(f"no data variable {variable!r}")
    for v in candidates:
        last = coords.get(v.dims[-1]) if v.dims else None
        if isinstance(last, LinearCoordinate) and not any(d in coords for d in v.dims[:-1]):
            return v, last
    what = f"data variable {variable!r}" if variable else "data variable"
    raise ValueError(
        f"no {what} is a trace: a linear coordinate on its last dim and none on the others"
    )


def trace_output(
    result_id: str,
    source: Dataset,
    time: LinearCoordinate,
    unit: str,
    fitted: np.ndarray,
    residual: np.ndarray,
    annotations: list[Annotation],
    created_at: datetime,
) -> Payload:
    """The fitted curve and the residual over the record's time coordinate, as a Dataset of their own
    (`source.kind = "analysis"`, ADR 0031), with the markers drawn on it."""
    name = "exponential"
    dataset = Dataset(
        dataset_id=f"{result_id}-exponential",
        name=name,
        dims=(Dimension(name=time.dim, size=time.num),),
        coords=(time,),
        data_vars=(
            DataVariable(name="fit", dims=(time.dim,), unit=unit, dtype="float32"),
            DataVariable(name="residual", dims=(time.dim,), unit=unit, dtype="float32"),
        ),
        attrs={"of_dataset": source.dataset_id},
        source=SourceDescriptor(kind="analysis", label=name),
        created_at=created_at,
    )
    arrays = {"fit": fitted.astype(np.float32), "residual": residual.astype(np.float32)}
    drawn = tuple(a.model_copy(update={"dataset_id": dataset.dataset_id}) for a in annotations)
    return Payload(dataset, arrays, drawn, None, None)


def fit_exponential(
    record: MeasurementRecord,
    payload: Payload,
    *,
    variable: str = "",
    skip: float = 0.0,
    span: float = 0.0,
    min_r2: float = 0.5,
) -> Analysis:
    """Fit a single exponential to a trace after its edge.

    `variable` defaults to the first data variable that is a trace (a linear coordinate on its last
    dim, none on the others); leading dims are averaged over, ignoring NaN. The fit window starts
    `skip` after the detected edge (in the time coordinate's unit) and lasts `span` (0: to the end of
    the record). Raises ValueError when no such variable exists or `record` is not the payload's
    record. Returns `status="failed"` for a trace with no edge, a window with fewer than four finite
    points, a constant window, a fit that does not converge, or an exponential explaining less than
    `min_r2` of the window's variance. The output is the fitted curve and the residual over the
    record's time coordinate (NaN outside the window); None when the method failed before fitting.
    """
    method = FitModel(
        name=NAME,
        version=VERSION,
        parameters={"variable": variable, "skip": skip, "span": span, "min_r2": min_r2},
    )
    dataset = payload.dataset
    if record.plan_id != dataset.dataset_id:
        raise ValueError(
            f"record {record.record_id} is for {record.plan_id!r}, payload for {dataset.dataset_id!r}"
        )
    if skip < 0 or span < 0:
        raise ValueError("skip and span must not be negative")
    var, time = _pick_trace(payload, variable)
    y = np.asarray(payload.arrays[var.name], dtype=float)
    while y.ndim > 1:
        with np.errstate(all="ignore"):
            y = np.nanmean(y, axis=0)
    t = np.linspace(time.start, time.stop, time.num)
    result_id = uuid.uuid4().hex
    now = datetime.now(UTC)
    fitted = residual = None

    def done(status, message="", estimates=(), annotations=(), **attrs):
        result = AnalysisResult(
            result_id=result_id,
            record_id=record.record_id,
            dataset_id=dataset.dataset_id,
            method=method,
            method_sha256=method.content_sha256(),
            status=status,
            message=message,
            estimates=tuple(estimates),
            annotations=tuple(annotations),
            created_at=now,
            attrs={"variable": var.name, **attrs},
        )
        output = (
            trace_output(
                result_id, dataset, time, var.unit, fitted, residual, list(annotations), now
            )
            if fitted is not None
            else None
        )
        return Analysis(result, output)

    try:
        edge = detect_edge(y)
    except ValueError as e:
        return done("failed", str(e))
    t_edge = float(t[edge])
    window = (np.arange(t.size) > edge) & (t >= t_edge + skip)
    if span > 0:
        window &= t <= t_edge + skip + span
    if window.sum() < 4:
        return done("failed", "fewer than four points after the edge", t_edge=t_edge)
    first = int(np.argmax(window))
    try:
        curve = fit(t[window], y[window])
    except ValueError as e:
        return done("failed", str(e), t_edge=t_edge, t_start=float(t[first]))
    fitted = np.full(t.shape, np.nan)
    fitted[window] = curve.at(t[window])
    residual = np.where(window & np.isfinite(y), y - fitted, np.nan)
    common = {
        "t_edge": t_edge,
        "t_start": curve.t_start,
        "t_stop": float(t[window][-1]),
        "n_points": curve.n_points,
        "r2": curve.r2,
        "residual_rms": curve.residual_rms,
    }
    if curve.r2 < min_r2:
        return done(
            "failed",
            f"the exponential explains {curve.r2:.3f} of the variance, below {min_r2}",
            **common,
        )

    def err(v: float) -> float | None:
        return v if math.isfinite(v) else None

    y_unit, t_unit = var.unit, time.unit
    estimates = [
        Estimate(name="tau", value=curve.tau, stderr=err(curve.stderr[0]), unit=t_unit),
        Estimate(name="amplitude", value=curve.amplitude, stderr=err(curve.stderr[1]), unit=y_unit),
        Estimate(name="offset", value=curve.offset, stderr=err(curve.stderr[2]), unit=y_unit),
        Estimate(name="residual_rms", value=curve.residual_rms, unit=y_unit),
        Estimate(name="r2", value=curve.r2, unit=""),
    ]
    annotations = [
        Annotation(
            annotation_id=f"{result_id[:12]}-edge",
            dataset_id=dataset.dataset_id,
            kind="marker",
            coords=(time.name,),
            points=((curve.t_start,),),
            label="edge",
            attrs={"t_edge": t_edge},
        ),
        Annotation(
            annotation_id=f"{result_id[:12]}-tau",
            dataset_id=dataset.dataset_id,
            kind="marker",
            coords=(time.name,),
            points=((curve.t_start + curve.tau,),),
            label=f"τ = {curve.tau:.4g} {t_unit}".strip(),
            attrs={"tau": curve.tau},
        ),
    ]
    return done("ok", estimates=estimates, annotations=annotations, **common)
