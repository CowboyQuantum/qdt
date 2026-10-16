"""A charge sensor's Coulomb peak on a 1-D gate trace, and the wing it should sit on (ADR 0062).

At small bias a sensor SET's current against its gate is a train of thermally broadened peaks,
`I(V) = background + height · sech²((V − V_peak) / width)` (the derivative of a Fermi function; the
simulator's model, ADR 0030, reduces to it at linear-response bias). The sensor detects charge best
where that current changes fastest with gate voltage: not on the peak, where the slope is zero, but on
its wing, at `V_peak ± atanh(1/√3) · width ≈ V_peak ± 0.66 width`, the inflection of sech². That point,
with its standard error, is what a tune-up parks the sensor gate at; the slope there,
`4 / (3√3) · height / width`, is the sensor's sensitivity.

1. **Trace**: the variable's last dim is the gate, on a `LinearCoordinate`; leading dims (shots,
   repeats) carry no coordinate and are averaged over, ignoring NaN.
2. **Peak**: local maxima of the lightly smoothed trace that rise at least a quarter of the trace's
   range above its 10th percentile; the one nearest `near_v` (or the trace's centre with
   `near_centre`) is the peak. No candidate is `failed`.
3. **Window**: from the nearest local minimum of the smoothed trace on each side of the peak (or the
   trace's end), so a neighbouring peak does not pull the fit.
4. **Fit** `background + height · sech²((V − V_peak) / width)` by nonlinear least squares from the
   half-maximum width, with standard errors from the covariance.
5. **Judge**: fewer than six finite points in the window, a fit that does not converge, a width or a
   height that is not positive, or a fit explaining less than `min_r2` of the window's variance is
   `failed`.

Estimates: `peak_v`, `width_v`, `height_a`, `background_a` (with standard errors), `wing_v` (the
operating point on the `side` asked, its error from the peak's and the width's), `sensitivity_a_per_v`,
`r2`, `residual_rms`. Overlays: `marker`s on the gate coordinate at the peak and at the wing. The
output is the fitted curve and the residual over the window (ADR 0031). Pure (rule 5).
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
    Dataset,
    DataVariable,
    Dimension,
    LinearCoordinate,
    SourceDescriptor,
)
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.modeling import AnalysisResult, Estimate, FitModel
from qdt_schemas.payload_hdf5 import Payload

from .exponential import _pick_trace
from .transitions import Analysis

NAME = "qdt_analysis.sensor_peak.fit_sensor_peak"
VERSION = "1"

WING_WIDTHS = math.atanh(1 / math.sqrt(3))
"""The wing in units of the width: where sech² is steepest (|d/du sech²(u)| is maximal at tanh²u = 1/3)."""
SLOPE_FACTOR = 4 / (3 * math.sqrt(3))
"""|dI/dV| at the wing = SLOPE_FACTOR · height / width."""
HALF_MAX_U = math.acosh(math.sqrt(2))
"""sech²(u) = 1/2 at u = ±acosh(√2): the full width at half maximum is 2·HALF_MAX_U · width."""
SIDES = ("above", "below")


class Peak(NamedTuple):
    """The least-squares `background + height · sech²((V − peak) / width)` and its figures of merit."""

    peak: float
    width: float
    height: float
    background: float
    stderr: tuple[float, float, float, float]
    """Standard errors of (peak, width, height, background); NaN where the covariance is not finite."""
    r2: float
    residual_rms: float
    n_points: int

    def at(self, v: np.ndarray) -> np.ndarray:
        return _model(v, self.peak, self.width, self.height, self.background)

    def wing(self, side: str) -> float:
        return self.peak + (WING_WIDTHS * self.width if side == "above" else -WING_WIDTHS * self.width)

    @property
    def wing_stderr(self) -> float:
        return math.hypot(self.stderr[0], WING_WIDTHS * self.stderr[1])

    @property
    def sensitivity(self) -> float:
        return SLOPE_FACTOR * self.height / self.width


def _model(v, peak, width, height, background):
    with np.errstate(over="ignore"):
        return background + height / np.cosh((v - peak) / width) ** 2


def find_peak(x: np.ndarray, y: np.ndarray, near: float) -> tuple[int, slice]:
    """Index of the Coulomb peak nearest `near` and the window (between the neighbouring minima of the
    smoothed trace) to fit it in. Raises ValueError when the trace has no peak."""
    finite = np.isfinite(y)
    if finite.sum() < 6:
        raise ValueError("a trace needs at least six finite points")
    filled = np.interp(np.arange(y.size), np.flatnonzero(finite), y[finite])
    width = max(1, y.size // 40)
    smooth = uniform_filter1d(filled, width, mode="nearest") if width > 1 else filled
    floor = float(np.percentile(smooth, 10))
    rise = float(smooth.max() - floor)
    if not rise > 0:
        raise ValueError("the trace is flat")
    left = np.r_[-np.inf, smooth[:-1]]
    right = np.r_[smooth[1:], -np.inf]
    maxima = np.flatnonzero((smooth >= left) & (smooth > right) & (smooth - floor >= 0.25 * rise))
    if maxima.size == 0:
        raise ValueError("the trace has no peak above a quarter of its range")
    i = int(maxima[np.argmin(np.abs(x[maxima] - near))])
    # the window: out from the peak to the first rise of the smoothed trace on each side
    lo = i
    while lo > 0 and smooth[lo - 1] <= smooth[lo]:
        lo -= 1
    hi = i
    while hi < y.size - 1 and smooth[hi + 1] <= smooth[hi]:
        hi += 1
    return i, slice(lo, hi + 1)


def fit_peak(x: np.ndarray, y: np.ndarray, i: int) -> Peak:
    """Nonlinear least squares of the sech² peak to the finite points of `y` over `x`, from the peak at
    index `i`. Raises ValueError with fewer than six finite points, a constant trace, or a fit that
    does not converge."""
    keep = np.isfinite(y)
    n = int(keep.sum())
    if n < 6:
        raise ValueError(f"only {n} finite point(s); a peak needs six")
    xx, yy = x[keep], y[keep]
    tss = float(((yy - yy.mean()) ** 2).sum())
    if tss == 0.0:
        raise ValueError("the window is constant")
    background0 = float(min(yy[0], yy[-1]))
    height0 = float(y[i] - background0) if np.isfinite(y[i]) else float(yy.max() - background0)
    if not height0 > 0:
        raise ValueError("the peak does not rise above the window's ends")
    half = background0 + height0 / 2
    above = np.flatnonzero(yy >= half)
    fwhm = float(xx[above[-1]] - xx[above[0]]) if above.size >= 2 else float(xx[-1] - xx[0]) / 4
    dx = float(abs(xx[-1] - xx[0])) / max(1, n - 1)
    width0 = max(fwhm / (2 * HALF_MAX_U), dx)
    span = float(abs(xx[-1] - xx[0]))
    try:
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", OptimizeWarning)
            coefficients, covariance = curve_fit(
                _model,
                xx,
                yy,
                p0=(float(x[i]), width0, height0, background0),
                bounds=(
                    [min(xx[0], xx[-1]), dx / 2, 0.0, -np.inf],
                    [max(xx[0], xx[-1]), 2 * span, np.inf, np.inf],
                ),
                maxfev=20000,
            )
    except (RuntimeError, ValueError) as e:
        raise ValueError(f"the fit did not converge: {e}") from None
    peak, width, height, background = (float(v) for v in coefficients)
    residual = yy - _model(xx, peak, width, height, background)
    rss = float(residual @ residual)
    with np.errstate(all="ignore"):
        stderr = tuple(float(v) for v in np.sqrt(np.diag(covariance)))
    return Peak(peak, width, height, background, stderr, 1.0 - rss / tss, math.sqrt(rss / n), n)


def _output(
    result_id: str,
    source: Dataset,
    gate: LinearCoordinate,
    unit: str,
    fitted: np.ndarray,
    residual: np.ndarray,
    annotations: list[Annotation],
    created_at: datetime,
) -> Payload:
    """The fitted peak and the residual over the record's gate coordinate (ADR 0031)."""
    name = "sensor peak"
    dataset = Dataset(
        dataset_id=f"{result_id}-sensor-peak",
        name=name,
        dims=(Dimension(name=gate.dim, size=gate.num),),
        coords=(gate,),
        data_vars=(
            DataVariable(name="fit", dims=(gate.dim,), unit=unit, dtype="float32"),
            DataVariable(name="residual", dims=(gate.dim,), unit=unit, dtype="float32"),
        ),
        attrs={"of_dataset": source.dataset_id},
        source=SourceDescriptor(kind="analysis", label=name),
        created_at=created_at,
    )
    arrays = {"fit": fitted.astype(np.float32), "residual": residual.astype(np.float32)}
    drawn = tuple(a.model_copy(update={"dataset_id": dataset.dataset_id}) for a in annotations)
    return Payload(dataset, arrays, drawn, None, None)


def fit_sensor_peak(
    record: MeasurementRecord,
    payload: Payload,
    *,
    variable: str = "",
    near_v: float = 0.0,
    near_centre: bool = True,
    side: str = "above",
    min_r2: float = 0.5,
) -> Analysis:
    """Fit the Coulomb peak of a sensor-gate trace and place the wing to sit on.

    `variable` defaults to the first data variable that is a trace (a linear coordinate on its last
    dim, none on the others); leading dims are averaged over, ignoring NaN. The peak fitted is the one
    nearest the trace's centre (`near_centre`) or `near_v`; `side` says which wing ('above': higher
    gate voltage). Raises ValueError when no such variable exists, `record` is not the payload's record
    or `side` is unknown. Returns `status="failed"` for a trace without a peak or a fit that does not
    hold (see the module docstring). The output is the fitted curve and the residual over the window
    (NaN outside); None when the method failed before fitting.
    """
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}, not {side!r}")
    method = FitModel(
        name=NAME,
        version=VERSION,
        parameters={
            "variable": variable,
            "near_v": near_v,
            "near_centre": near_centre,
            "side": side,
            "min_r2": min_r2,
        },
    )
    dataset = payload.dataset
    if record.plan_id != dataset.dataset_id:
        raise ValueError(
            f"record {record.record_id} is for {record.plan_id!r}, payload for {dataset.dataset_id!r}"
        )
    var, gate = _pick_trace(payload, variable)
    y = np.asarray(payload.arrays[var.name], dtype=float)
    while y.ndim > 1:
        with np.errstate(all="ignore"):
            y = np.nanmean(y, axis=0)
    x = np.linspace(gate.start, gate.stop, gate.num)
    target = float((gate.start + gate.stop) / 2) if near_centre else near_v
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
            attrs={"variable": var.name, "target_v": target, **attrs},
        )
        output = (
            _output(result_id, dataset, gate, var.unit, fitted, residual, list(annotations), now)
            if fitted is not None
            else None
        )
        return Analysis(result, output)

    try:
        i, window = find_peak(x, y, target)
    except ValueError as e:
        return done("failed", str(e))
    try:
        peak = fit_peak(x[window], y[window], i - window.start)
    except ValueError as e:
        return done("failed", str(e), peak_index=int(i))
    if not (peak.width > 0 and peak.height > 0):
        return done("failed", f"width {peak.width:.3g} and height {peak.height:.3g} must be positive")
    if peak.r2 < min_r2:
        return done("failed", f"the peak explains {peak.r2:.2f} of the window's variance, below {min_r2}")
    fitted = np.full(x.shape, np.nan)
    fitted[window] = peak.at(x[window])
    residual = np.where(np.isfinite(y) & np.isfinite(fitted), y - fitted, np.nan)
    wing = peak.wing(side)
    sensitivity_unit = f"{var.unit}/{gate.unit}" if var.unit and gate.unit else ""
    err = lambda v: float(v) if math.isfinite(v) else None
    estimates = [
        Estimate(name="peak_v", value=peak.peak, unit=gate.unit, stderr=err(peak.stderr[0])),
        Estimate(name="width_v", value=peak.width, unit=gate.unit, stderr=err(peak.stderr[1])),
        Estimate(name="height_a", value=peak.height, unit=var.unit, stderr=err(peak.stderr[2])),
        Estimate(name="background_a", value=peak.background, unit=var.unit, stderr=err(peak.stderr[3])),
        Estimate(name="wing_v", value=wing, unit=gate.unit, stderr=err(peak.wing_stderr)),
        Estimate(name="sensitivity_a_per_v", value=peak.sensitivity, unit=sensitivity_unit),
        Estimate(name="r2", value=peak.r2, unit=""),
        Estimate(name="residual_rms", value=peak.residual_rms, unit=var.unit),
    ]
    annotations = [
        Annotation(
            annotation_id=f"{result_id[:12]}-{label}",
            dataset_id=dataset.dataset_id,
            kind="marker",
            coords=(gate.name,),
            points=((value,),),
            label=label,
        )
        for label, value in (("peak", peak.peak), ("wing", wing))
    ]
    return done(
        "ok",
        f"peak at {peak.peak:+.4f} {gate.unit}, width {peak.width:.4f}; wing {side} at {wing:+.4f}",
        estimates,
        annotations,
        window_start=float(x[window][0]),
        window_stop=float(x[window][-1]),
        n_points=peak.n_points,
        side=side,
    )
