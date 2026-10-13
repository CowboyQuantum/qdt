"""Charge-transition line detection on a 2-D stability diagram: Step 4's first consumer (ADR 0029).

Detection and estimation are separate stages (plan, Step 4):

- `detect` scales the map robustly, smooths it, takes the gradient, keeps ridge pixels above a threshold,
  groups them into orientation *families* (the addition lines of one dot share an orientation; a
  honeycomb has two) and labels the connected runs within each family. Pixels whose gradient points
  between families (vertices, interdot transitions) belong to no family and split the runs.
- `estimate` fits one straight segment per run by weighted total least squares, merges collinear runs,
  and reports endpoints in pixel units.
- `charge_transitions` does both for a `Dataset` and its arrays, converts endpoints to the Dataset's
  coordinates, and returns an `AnalysisResult` whose annotations are the segments.

Everything here is a pure function of its arguments (rule 5): no file, socket or registry is touched.
"""

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from scipy import ndimage

from qdt_schemas.data import (
    Annotation,
    Dataset,
    IndexedCoordinate,
    LinearCoordinate,
    StreamedCoordinate,
)
from qdt_schemas.modeling import AnalysisResult, FitModel, MeasurementRef, ScenarioRef

from . import __version__

MODEL_NAME = "charge_transition_lines"

DEFAULTS: dict[str, float | int] = {
    "sigma": 1.0,
    "level": 0.3,
    "noise_sigmas": 4.0,
    "n_families": 2,
    "angle_tolerance_deg": 20.0,
    "min_pixels": 6,
    "merge_tolerance": 1.0,
    "merge_gap": 6.0,
}
"""Detector parameters and their defaults; `charge_transitions(**overrides)` records what it used.

sigma: Gaussian smoothing (pixels) before the gradient; 0 disables.
level: ridge threshold as a fraction of the 99th percentile of the gradient magnitude.
noise_sigmas: ridge threshold floor, in standard deviations of the gradient noise (pixel noise
    estimated from a median-filter residual, propagated through the smoothing).
n_families: at most this many orientation families (two for a double dot).
angle_tolerance_deg: a pixel joins a family when its gradient is within this angle of the family's.
min_pixels: runs with fewer pixels are noise and are dropped.
merge_tolerance: collinear runs of one family within this perpendicular distance (pixels) are one line;
    0 disables merging.
merge_gap: runs merge only when the gap between them along the line is at most this (pixels), so
    collinear edges of distant honeycomb cells stay separate.
"""


@dataclass(frozen=True)
class Detection:
    """Stage 1 output, all arrays with the map's shape."""

    gradient: np.ndarray
    """Gradient magnitude of the scaled, smoothed map."""
    orientation: np.ndarray
    """Gradient direction in [0, π): the normal of the local edge."""
    mask: np.ndarray
    """Ridge pixels (gradient above threshold)."""
    families: tuple[float, ...]
    """Family orientations in [0, π), strongest first."""
    family_of: np.ndarray
    """Family index per pixel; -1 where none."""
    labels: np.ndarray
    """Run index per pixel, 1..n_runs; 0 where none."""


@dataclass(frozen=True)
class Segment:
    """Stage 2 output: one straight transition line in pixel units (row, col)."""

    family: int
    start: tuple[float, float]
    stop: tuple[float, float]
    strength: float
    """Mean gradient magnitude along the run (scaled-map units per pixel)."""
    n_pixels: int


def _axial_distance(theta: np.ndarray, phi: float) -> np.ndarray:
    """Smallest angle between orientations modulo π."""
    d = np.mod(theta - phi, np.pi)
    return np.minimum(d, np.pi - d)


def _families(theta: np.ndarray, weight: np.ndarray, n: int, tol: float) -> tuple[float, ...]:
    """Up to `n` dominant orientations of weighted axial data, each refined by an axial mean."""
    if theta.size == 0:
        return ()
    bins = 36
    hist, edges = np.histogram(theta, bins=bins, range=(0.0, np.pi), weights=weight)
    hist = (np.roll(hist, 1) + 2 * hist + np.roll(hist, -1)) / 4  # circular smoothing
    centres = (edges[:-1] + edges[1:]) / 2
    found: list[float] = []
    first = None
    for _ in range(n):
        k = int(np.argmax(hist))
        if hist[k] <= 0 or (first is not None and hist[k] < 0.05 * first):
            break
        first = first if first is not None else hist[k]
        phi = float(centres[k])
        sel = _axial_distance(theta, phi) <= tol
        if sel.any():
            phi = float(np.mod(0.5 * np.angle(np.sum(weight[sel] * np.exp(2j * theta[sel]))), np.pi))
        found.append(phi)
        hist[_axial_distance(centres, phi) <= tol] = 0
    return tuple(found)


def _noise_sigma(zs: np.ndarray) -> float:
    """Pixel noise of a map (robust): spread of the residual against a 3×3 median filter."""
    resid = zs - ndimage.median_filter(zs, size=3, mode="nearest")
    return 1.4826 * float(np.median(np.abs(resid)))


def _gradient_gain(sigma: float) -> float:
    """Noise gain of one gradient component after Gaussian smoothing: ‖∂(G_σ)‖₂ on the pixel grid."""
    n = 2 * math.ceil(4 * sigma) + 5
    impulse = np.zeros((n, n))
    impulse[n // 2, n // 2] = 1.0
    h = ndimage.gaussian_filter(impulse, sigma) if sigma > 0 else impulse
    _, hx = np.gradient(h)
    return float(np.sqrt((hx**2).sum()))


def detect(
    z: np.ndarray,
    *,
    sigma: float = DEFAULTS["sigma"],
    level: float = DEFAULTS["level"],
    noise_sigmas: float = DEFAULTS["noise_sigmas"],
    n_families: int = DEFAULTS["n_families"],
    angle_tolerance_deg: float = DEFAULTS["angle_tolerance_deg"],
    min_pixels: int = DEFAULTS["min_pixels"],
) -> Detection:
    """Stage 1 on a 2-D map `z` (rows, cols). NaN cells (unwritten) take their nearest written value
    and their neighbourhood is excluded from the ridge mask."""
    z = np.asarray(z, dtype=float)
    if z.ndim != 2:
        raise ValueError(f"detect needs a 2-D map, got shape {z.shape}")
    finite = np.isfinite(z)
    if not finite.any():
        raise ValueError("map has no finite values")
    median = float(np.median(z[finite]))
    mad = float(np.median(np.abs(z[finite] - median)))
    scale = 1.4826 * mad or float(z[finite].std()) or 1.0
    zs = (z - median) / scale
    if not finite.all():  # unwritten cells take their nearest written value: no false edge
        nearest = ndimage.distance_transform_edt(~finite, return_distances=False, return_indices=True)
        zs = zs[tuple(nearest)]
    noise = _noise_sigma(zs)
    if sigma > 0:
        zs = ndimage.gaussian_filter(zs, sigma, mode="nearest")
    gy, gx = np.gradient(zs)
    g = np.hypot(gx, gy)
    theta = np.mod(np.arctan2(gy, gx), np.pi)
    threshold = max(level * float(np.percentile(g, 99)), noise_sigmas * noise * _gradient_gain(sigma))
    mask = g > threshold
    if not finite.all():
        reach = math.ceil(2 * sigma) + 1
        mask &= ndimage.binary_erosion(finite, iterations=reach, border_value=1)
    tol = math.radians(angle_tolerance_deg)
    families = _families(theta[mask], g[mask], n_families, tol)
    family_of = np.full(z.shape, -1, dtype=int)
    if families:
        dist = np.stack([_axial_distance(theta, phi) for phi in families])  # (k, rows, cols)
        nearest = dist.argmin(axis=0)
        within = dist.min(axis=0) <= tol
        family_of[mask & within] = nearest[mask & within]
    labels = np.zeros(z.shape, dtype=int)
    n_runs = 0
    eight = np.ones((3, 3), dtype=bool)
    for k in range(len(families)):
        lab, n = ndimage.label(family_of == k, structure=eight)
        if n == 0:
            continue
        sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
        for i, size in enumerate(sizes, start=1):
            if size >= min_pixels:
                n_runs += 1
                labels[lab == i] = n_runs
            else:
                family_of[lab == i] = -1
    return Detection(g, theta, mask, families, family_of, labels)


def _fit(rows: np.ndarray, cols: np.ndarray, weight: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Weighted total-least-squares line through pixels: (centroid, unit direction) with col ≥ 0."""
    w = weight / weight.sum()
    centre = np.array([np.dot(w, rows), np.dot(w, cols)])
    dr, dc = rows - centre[0], cols - centre[1]
    cov = np.array([[np.dot(w, dr * dr), np.dot(w, dr * dc)], [np.dot(w, dr * dc), np.dot(w, dc * dc)]])
    values, vectors = np.linalg.eigh(cov)
    d = vectors[:, int(np.argmax(values))]
    if d[1] < 0 or (d[1] == 0 and d[0] < 0):
        d = -d
    return centre, d


def _segment(
    family: int, rows: np.ndarray, cols: np.ndarray, weight: np.ndarray
) -> tuple[Segment, np.ndarray, np.ndarray]:
    centre, d = _fit(rows, cols, weight)
    t = (rows - centre[0]) * d[0] + (cols - centre[1]) * d[1]
    start, stop = centre + t.min() * d, centre + t.max() * d
    seg = Segment(
        family,
        (float(start[0]), float(start[1])),
        (float(stop[0]), float(stop[1])),
        float(weight.mean()),
        int(rows.size),
    )
    return seg, centre, d


def _perpendicular(point: np.ndarray, centre: np.ndarray, d: np.ndarray) -> float:
    v = point - centre
    return abs(float(v[0] * d[1] - v[1] * d[0]))


def estimate(
    detection: Detection,
    *,
    merge_tolerance: float = DEFAULTS["merge_tolerance"],
    merge_gap: float = DEFAULTS["merge_gap"],
) -> list[Segment]:
    """Stage 2: one segment per run; runs of a family are merged and refitted when the shorter lies on
    the longer's line within `merge_tolerance` (the longer run's direction is the better determined)."""
    runs: list[tuple[int, np.ndarray, np.ndarray]] = []
    for i in range(1, int(detection.labels.max()) + 1):
        rows, cols = np.nonzero(detection.labels == i)
        runs.append((int(detection.family_of[rows[0], cols[0]]), rows, cols))
    fits = [_segment(f, r, c, detection.gradient[r, c]) for f, r, c in runs]
    parent = list(range(len(runs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    if merge_tolerance > 0:
        for i in range(len(runs)):
            for j in range(i + 1, len(runs)):
                if runs[i][0] != runs[j][0]:
                    continue
                longer, shorter = sorted((fits[i], fits[j]), key=lambda f: -f[0].n_pixels)
                seg, centre, d = longer
                ends = (np.array(shorter[0].start), np.array(shorter[0].stop))
                if any(_perpendicular(p, centre, d) > merge_tolerance for p in ends):
                    continue
                along = [float(np.dot(p - centre, d)) for p in ends]
                own = [float(np.dot(np.array(p) - centre, d)) for p in (seg.start, seg.stop)]
                if max(min(along) - max(own), min(own) - max(along)) <= merge_gap:
                    parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(runs)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) == 1:
            out.append(fits[members[0]][0])
            continue
        rows = np.concatenate([runs[m][1] for m in members])
        cols = np.concatenate([runs[m][2] for m in members])
        out.append(_segment(runs[members[0]][0], rows, cols, detection.gradient[rows, cols])[0])
    out.sort(key=lambda s: (s.family, s.start[0], s.start[1]))
    return out


def axis_values(
    dataset: Dataset, arrays: Mapping[str, np.ndarray], dim: str
) -> tuple[str, np.ndarray]:
    """(coordinate name, values) of the coordinate labelling `dim`; raises if none does."""
    for c in dataset.coords:
        if c.dim != dim:
            continue
        if isinstance(c, LinearCoordinate):
            return c.name, np.linspace(c.start, c.stop, c.num)
        if isinstance(c, IndexedCoordinate):
            return c.name, np.asarray(c.values, dtype=float)
        if isinstance(c, StreamedCoordinate):
            return c.name, np.asarray(arrays[c.name], dtype=float)
    raise ValueError(f"dimension {dim!r} has no coordinate; a transition line needs data coordinates")


def map_of(
    dataset: Dataset, arrays: Mapping[str, np.ndarray], variable: str | None = None
) -> tuple[str, np.ndarray, tuple[str, str]]:
    """(variable, 2-D map, (row dim, col dim)); a leading repeat dimension is averaged, NaN-aware."""
    candidates = [v for v in dataset.data_vars if len(v.dims) in (2, 3)]
    if variable is not None:
        candidates = [v for v in candidates if v.name == variable]
    if not candidates:
        raise ValueError(f"no 2-D (or repeated 2-D) variable {variable or ''} in {dataset.name!r}")
    v = candidates[0]
    z = np.asarray(arrays[v.name], dtype=float)
    if z.ndim == 3:
        with np.errstate(invalid="ignore"):
            z = np.nanmean(z, axis=0)
    return v.name, z, (v.dims[-2], v.dims[-1])


def charge_transitions(
    dataset: Dataset,
    arrays: Mapping[str, np.ndarray],
    scenario: ScenarioRef,
    *,
    variable: str | None = None,
    record_id: str | None = None,
    analysis_id: str | None = None,
    created_at: datetime | None = None,
    **parameters: float,
) -> AnalysisResult:
    """Detect charge-transition lines on `dataset`'s 2-D map and return them as line annotations.

    `scenario` is the generator of the data (mandatory provenance, ADR 0029); `record_id` is the
    registry record when the Dataset has one. Keyword `parameters` override `DEFAULTS`.
    """
    unknown = set(parameters) - set(DEFAULTS)
    if unknown:
        raise TypeError(f"unknown detector parameters {sorted(unknown)}; see DEFAULTS")
    params: dict[str, float | int] = {**DEFAULTS, **parameters}
    name, z, (row_dim, col_dim) = map_of(dataset, arrays, variable)
    merging = {"merge_tolerance", "merge_gap"}
    detection = detect(z, **{k: v for k, v in params.items() if k not in merging})
    segments = estimate(detection, **{k: params[k] for k in merging})
    row_name, rows = axis_values(dataset, arrays, row_dim)
    col_name, cols = axis_values(dataset, arrays, col_dim)
    analysis_id = analysis_id or uuid.uuid4().hex

    def to_data(p: tuple[float, float]) -> tuple[float, float]:
        return (
            float(np.interp(p[0], np.arange(rows.size), rows)),
            float(np.interp(p[1], np.arange(cols.size), cols)),
        )

    annotations = []
    for k, s in enumerate(segments):
        p0, p1 = to_data(s.start), to_data(s.stop)
        annotations.append(
            Annotation(
                annotation_id=f"{analysis_id}:{k}",
                dataset_id=dataset.dataset_id,
                kind="line",
                coords=(row_name, col_name),
                points=(p0, p1),
                label=f"f{s.family}",
                attrs={
                    "family": s.family,
                    "angle_deg": math.degrees(math.atan2(p1[0] - p0[0], p1[1] - p0[1])),
                    "strength": s.strength,
                    "n_pixels": s.n_pixels,
                },
            )
        )
    summary: dict[str, float | int] = {
        "n_lines": len(segments),
        "n_families": len(detection.families),
        "ridge_fraction": float(detection.mask.mean()),
    }
    for k, phi in enumerate(detection.families):
        members = [s for s in segments if s.family == k]
        if members:  # the segments' normals, pixel-weighted, beat the histogram estimate
            normals = [
                math.atan2(s.stop[0] - s.start[0], s.stop[1] - s.start[1]) + math.pi / 2
                for s in members
            ]
            weights = [s.n_pixels for s in members]
            phi = 0.5 * np.angle(np.sum(np.array(weights) * np.exp(2j * np.array(normals)))) % math.pi
        summary[f"family_{k}_orientation_deg"] = math.degrees(phi)
        summary[f"family_{k}_lines"] = len(members)
    return AnalysisResult(
        analysis_id=analysis_id,
        model=FitModel(name=MODEL_NAME, version=__version__, parameters=params),
        measurement=MeasurementRef(dataset_id=dataset.dataset_id, variable=name, record_id=record_id),
        scenario=scenario,
        annotations=tuple(annotations),
        summary=summary,
        created_at=created_at or datetime.now(UTC),
    )
