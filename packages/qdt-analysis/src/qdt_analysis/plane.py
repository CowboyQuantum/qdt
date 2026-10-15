"""A plane through a 2-D map: `z = slope_row · x + slope_col · y + offset`, with iso-lines as overlays.

The L2-1 oracle (BENCH.md, ADR 0040): a DC level stepped on the outer axis and a pulse amplitude swept
on the inner one, summed through a passive network and read at a sink, give a plane
`V = c_DC · V_DC + c_P · V_pulse + offset`. Its iso-voltage lines, of slope `−c_DC / c_P` in the
(row, col) plane, are the analogue of a charge transition: the overlay Flight Deck draws.

1. **Fit** by ordinary least squares over the finite points, with standard errors from the residual
   variance (`N − 3` degrees of freedom). Leading dims (repeat, shot) are averaged over first.
2. **Judge**: the plane must explain at least `min_r2` of the map's variance, or the result is
   `failed`: a noise map, or a constant one, has no plane to report, and a map that is mostly structure
   (a stability diagram) is not what this method is for.
3. **Overlay** `n_isolines` iso-lines at evenly spaced levels strictly between the fitted plane's
   extremes over the window, each clipped to the window and labelled with its level.

Estimates: `slope_row`, `slope_col`, `offset` (with standard errors), `isoline_slope`
(`−slope_row / slope_col`, columns per row), `residual_rms` and `r2`. The output payload is the fitted
plane and the residual over the input's coordinates (ADR 0031). Pure (rule 5).
"""

import math
import uuid
from datetime import UTC, datetime
from typing import NamedTuple

import numpy as np

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

from .transitions import Analysis, _pick

NAME = "qdt_analysis.plane.fit_plane"
VERSION = "1"


class Plane(NamedTuple):
    """The least-squares plane `z = slope_row · x + slope_col · y + offset` and its figures of merit."""

    slope_row: float
    slope_col: float
    offset: float
    stderr: tuple[float, float, float]
    """Standard errors of (slope_row, slope_col, offset)."""
    covariance: np.ndarray
    """3 × 3 covariance of (slope_row, slope_col, offset)."""
    r2: float
    """Fraction of the map's variance the plane explains; NaN for a constant map."""
    residual_rms: float
    n_points: int

    def at(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """The plane on the grid `x` (rows) × `y` (columns)."""
        return self.slope_row * x[:, None] + self.slope_col * y[None, :] + self.offset


def fit(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> Plane:
    """Ordinary least squares of the finite points of `image` (rows over `x`, columns over `y`).

    Raises ValueError with fewer than four finite points or a rank-deficient design (a single row or
    column, or all finite points on one line).
    """
    gx, gy = np.meshgrid(x, y, indexing="ij")
    keep = np.isfinite(image)
    n = int(keep.sum())
    if n < 4:
        raise ValueError(f"only {n} finite point(s); a plane needs four")
    design = np.column_stack([gx[keep], gy[keep], np.ones(n)])
    z = image[keep]
    coefficients, _, rank, _ = np.linalg.lstsq(design, z, rcond=None)
    if rank < 3:
        raise ValueError("the finite points do not span a plane")
    residual = z - design @ coefficients
    rss = float(residual @ residual)
    sigma2 = rss / (n - 3)
    covariance = sigma2 * np.linalg.inv(design.T @ design)
    tss = float(((z - z.mean()) ** 2).sum())
    r2 = 1.0 - rss / tss if tss > 0 else math.nan
    a, b, c = (float(v) for v in coefficients)
    return Plane(
        a,
        b,
        c,
        tuple(float(v) for v in np.sqrt(np.diag(covariance))),
        covariance,
        r2,
        math.sqrt(rss / n),
        n,
    )


def isoline(
    plane: Plane, level: float, x: tuple[float, float], y: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The segment where the plane equals `level` inside the window `x` × `y`, as two (row, col)
    points, or None when the line misses the window or the plane is flat."""
    a, b, c = plane.slope_row, plane.slope_col, level - plane.offset  # a · x + b · y = c
    x0, x1 = sorted(x)
    y0, y1 = sorted(y)
    eps_x, eps_y = 1e-9 * max(x1 - x0, 1e-300), 1e-9 * max(y1 - y0, 1e-300)
    candidates: list[tuple[float, float]] = []
    if b != 0:
        for xe in (x0, x1):
            ye = (c - a * xe) / b
            if y0 - eps_y <= ye <= y1 + eps_y:
                candidates.append((xe, min(max(ye, y0), y1)))
    if a != 0:
        for ye in (y0, y1):
            xe = (c - b * ye) / a
            if x0 - eps_x <= xe <= x1 + eps_x:
                candidates.append((min(max(xe, x0), x1), ye))
    distinct: list[tuple[float, float]] = []
    for p in candidates:
        if all(abs(p[0] - q[0]) > eps_x or abs(p[1] - q[1]) > eps_y for q in distinct):
            distinct.append(p)
    if len(distinct) < 2:
        return None
    p, q = max(
        ((p, q) for i, p in enumerate(distinct) for q in distinct[i + 1 :]),
        key=lambda pq: math.hypot(
            (pq[0][0] - pq[1][0]) / max(x1 - x0, 1e-300), (pq[0][1] - pq[1][1]) / max(y1 - y0, 1e-300)
        ),
    )
    return (float(p[0]), float(p[1])), (float(q[0]), float(q[1]))


def plane_map(
    result_id: str,
    source: Dataset,
    row: LinearCoordinate,
    col: LinearCoordinate,
    unit: str,
    fitted: np.ndarray,
    residual: np.ndarray,
    annotations: list[Annotation],
    created_at: datetime,
) -> Payload:
    """The fitted plane and the residual as a Dataset over the input's coordinates, with the iso-lines
    drawn on it (ADR 0031)."""
    name = "fitted plane"
    dataset = Dataset(
        dataset_id=f"{result_id}-plane",
        name=name,
        dims=(Dimension(name=row.dim, size=row.num), Dimension(name=col.dim, size=col.num)),
        coords=(row, col),
        data_vars=(
            DataVariable(name="fit", dims=(row.dim, col.dim), unit=unit, dtype="float32"),
            DataVariable(name="residual", dims=(row.dim, col.dim), unit=unit, dtype="float32"),
        ),
        attrs={"of_dataset": source.dataset_id},
        source=SourceDescriptor(kind="analysis", label=name),
        created_at=created_at,
    )
    arrays = {"fit": fitted.astype(np.float32), "residual": residual.astype(np.float32)}
    drawn = tuple(a.model_copy(update={"dataset_id": dataset.dataset_id}) for a in annotations)
    return Payload(dataset, arrays, drawn, None, None)


def fit_plane(
    record: MeasurementRecord,
    payload: Payload,
    *,
    variable: str = "",
    n_isolines: int = 8,
    min_r2: float = 0.5,
) -> Analysis:
    """Fit a plane to a 2-D map and draw its iso-lines.

    `variable` defaults to the first data variable whose last two dims carry linear coordinates; the
    row coordinate is `x`, the column coordinate `y`. Leading dims are averaged over, ignoring NaN.
    Raises ValueError when no such variable exists or `record` is not the payload's record. Returns
    `status="failed"` for a map with fewer than 2 × 2 points, fewer than half its points finite, a
    constant map, or a plane explaining less than `min_r2` of the variance. The output is the fitted
    plane and the residual over the input's coordinates; None when the method failed before fitting.
    """
    method = FitModel(
        name=NAME,
        version=VERSION,
        parameters={"variable": variable, "n_isolines": n_isolines, "min_r2": min_r2},
    )
    dataset = payload.dataset
    if record.plan_id != dataset.dataset_id:
        raise ValueError(
            f"record {record.record_id} is for {record.plan_id!r}, payload for {dataset.dataset_id!r}"
        )
    var, row, col = _pick(payload, variable)
    image = np.asarray(payload.arrays[var.name], dtype=float)
    while image.ndim > 2:
        with np.errstate(all="ignore"):
            image = np.nanmean(image, axis=0)
    x = np.linspace(row.start, row.stop, row.num)
    y = np.linspace(col.start, col.stop, col.num)
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
            plane_map(result_id, dataset, row, col, var.unit, fitted, residual, list(annotations), now)
            if fitted is not None
            else None
        )
        return Analysis(result, output)

    if min(image.shape) < 2:
        return done("failed", "map smaller than 2 × 2 points")
    finite = np.isfinite(image)
    if finite.mean() < 0.5:
        return done("failed", "fewer than half the points are finite")
    try:
        plane = fit(image, x, y)
    except ValueError as e:
        return done("failed", str(e))
    if math.isnan(plane.r2):
        return done("failed", "the map is constant", n_points=plane.n_points)
    fitted = plane.at(x, y)
    residual = np.where(finite, image - fitted, np.nan)
    if plane.r2 < min_r2:
        return done(
            "failed",
            f"the plane explains {plane.r2:.3f} of the variance, below {min_r2}",
            n_points=plane.n_points,
            r2=plane.r2,
            residual_rms=plane.residual_rms,
        )

    z_unit, x_unit, y_unit = var.unit, row.unit, col.unit

    def per(unit: str) -> str:
        return f"{z_unit}/{unit}" if z_unit and unit else ""

    a, b = plane.slope_row, plane.slope_col
    cov = plane.covariance
    estimates = [
        Estimate(name="slope_row", value=a, stderr=plane.stderr[0], unit=per(x_unit)),
        Estimate(name="slope_col", value=b, stderr=plane.stderr[1], unit=per(y_unit)),
        Estimate(name="offset", value=plane.offset, stderr=plane.stderr[2], unit=z_unit),
        Estimate(name="residual_rms", value=plane.residual_rms, unit=z_unit),
        Estimate(name="r2", value=plane.r2, unit=""),
    ]
    # Iso-lines run along the columns when slope_col is zero: no finite slope to report. "Zero" is
    # relative: the column term must move the plane by less than 1e-9 of the row term over the window.
    along_columns = abs(b) * abs(y[-1] - y[0]) <= 1e-9 * abs(a) * abs(x[-1] - x[0])
    if not along_columns:
        # var(−a/b) by first-order propagation, with the covariance of a and b
        var_iso = (cov[0, 0] / b**2) + (a**2 * cov[1, 1] / b**4) - (2 * a * cov[0, 1] / b**3)
        estimates.append(
            Estimate(
                name="isoline_slope",
                value=-a / b,
                stderr=math.sqrt(max(var_iso, 0.0)),
                unit=f"{y_unit}/{x_unit}" if x_unit and y_unit else "",
            )
        )
    corners = plane.at(np.array([x[0], x[-1]]), np.array([y[0], y[-1]]))
    levels = np.linspace(corners.min(), corners.max(), n_isolines + 2)[1:-1]
    annotations: list[Annotation] = []
    for k, level in enumerate(levels):
        segment = isoline(plane, float(level), (x[0], x[-1]), (y[0], y[-1]))
        if segment is None:
            continue
        annotations.append(
            Annotation(
                annotation_id=f"{result_id[:12]}-iso-{k}",
                dataset_id=dataset.dataset_id,
                kind="line",
                coords=(row.name, col.name),
                points=segment,
                label=f"{level:.4g} {z_unit}".strip(),
                attrs={"level": float(level)},
            )
        )
    return done(
        "ok",
        estimates=estimates,
        annotations=annotations,
        n_points=plane.n_points,
        r2=plane.r2,
        residual_rms=plane.residual_rms,
        n_isolines=len(annotations),
    )
