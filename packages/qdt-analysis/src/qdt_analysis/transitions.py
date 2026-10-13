"""Charge transitions on a stability diagram: detect the segments, estimate the honeycomb lattice (ADR 0029).

Detection and estimation are separate stages, with separate jobs:

1. **Detect** transition pixels (what the overlay shows). The gradient magnitude of the Gaussian-smoothed map
   must exceed both `threshold_rel` × its 99.5th percentile and `threshold_noise` × the gradient noise
   (estimated from the MAD of pixel-to-pixel differences), and must be a ridge maximum across the edge
   (non-maximum suppression, so lines are one pixel wide). A median-based threshold fails here because
   transitions cover too large a fraction of a dense map. The ridge pixels split into two families by
   gradient direction, and each 8-connected run long enough becomes a `line` Annotation along its
   principal axis.
2. **Estimate** the charge lattice (what the numbers are). In the constant-interaction picture the
   honeycomb repeats whenever the gate-induced charge on one dot changes by one electron, so its
   reciprocal lattice vectors are the rows of C_gate / e: electrons per volt on each dot from each gate.
   They are the two shortest non-collinear peaks of the power spectrum of the windowed gradient-magnitude
   image (zero-padded, parabolic sub-bin interpolation). This uses the whole map and has no pixel-grid
   bias. Per-segment slope fits do, on short jagged segments. Reported per dot, labelled by its dominant
   gate: `a` is dominated by the row gate, `b` by the column gate.

Pure: schema objects and arrays in, `AnalysisResult` out (rule 5).
"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d, label, maximum_filter

from qdt_schemas.data import Annotation, LinearCoordinate
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.modeling import AnalysisResult, Estimate, FitModel
from qdt_schemas.payload_hdf5 import Payload

NAME = "qdt_analysis.transitions.detect_transitions"
VERSION = "1"


@dataclass(frozen=True)
class Segments:
    """The detection stage's output: ridge pixels and the straight segments found on them."""

    magnitude: np.ndarray
    """Gradient magnitude of the smoothed map (rows, cols)."""
    edges: np.ndarray
    """Ridge pixels above threshold (bool, rows × cols)."""
    threshold: float
    noise: float
    """Estimated pixel noise of the map."""
    families: tuple[tuple[str, float], ...]
    """(label, normal angle) of the gradient-direction families, strongest first."""
    segments: tuple[tuple[str, tuple[float, float], tuple[float, float]], ...]
    """(family, start, stop) per 8-connected run, endpoints in data coordinates (row, col)."""


def detect_segments(
    image: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    *,
    smooth_px: float = 1.0,
    threshold_rel: float = 0.3,
    threshold_noise: float = 5.0,
    min_separation_deg: float = 15.0,
    window_deg: float = 12.0,
    min_segment_px: int = 6,
    max_segments: int = 200,
    family_space: str = "voltage",
) -> Segments:
    """Stage 1 on a finite 2-D map with linear row coordinates `x` and column coordinates `y`:
    smoothed gradient, relative + noise-floor threshold, non-maximum suppression, two gradient-direction
    families, one straight segment per 8-connected run. Shared by every edge-based method (diamonds reuse
    it, ADR 0030).

    `family_space` says where gradient directions are compared: `"voltage"` (physical slopes; the
    honeycomb's steep/shallow lines) or `"pixel"` (the map as drawn; needed when the two axes span very
    different ranges, as a bias axis of millivolts against a gate axis of hundreds of millivolts, where
    voltage-space normals of distinct edge families nearly coincide)."""
    dx = (x[-1] - x[0]) / (len(x) - 1) if len(x) > 1 else 0.0
    dy = (y[-1] - y[0]) / (len(y) - 1) if len(y) > 1 else 0.0
    g_r = gaussian_filter(image, smooth_px, order=(1, 0))
    g_c = gaussian_filter(image, smooth_px, order=(0, 1))
    mag = np.hypot(g_r, g_c)
    diffs = np.concatenate([np.diff(image, axis=0).ravel(), np.diff(image, axis=1).ravel()])
    sigma = 1.4826 * float(np.median(np.abs(diffs - np.median(diffs)))) / math.sqrt(2)
    threshold = max(
        threshold_rel * float(np.percentile(mag, 99.5)),
        threshold_noise * sigma * _derivative_gain(smooth_px),
    )
    edges = (mag > threshold) & _ridge(mag, g_r, g_c)
    if family_space == "voltage":
        theta = np.mod(np.arctan2(g_c / dy, g_r / dx), np.pi)  # normal direction in voltage space
    elif family_space == "pixel":
        theta = np.mod(np.arctan2(g_c, g_r), np.pi)
    else:
        raise ValueError(f"family_space is 'voltage' or 'pixel', not {family_space!r}")
    families = tuple(_families(theta[edges], mag[edges], min_separation_deg)) if edges.any() else ()
    segments: list[tuple[str, tuple[float, float], tuple[float, float]]] = []
    for family, normal in families:
        mask = edges & (
            np.abs(np.angle(np.exp(2j * (theta - normal)))) / 2 < math.radians(window_deg)
        )
        labels, n = label(mask, structure=np.ones((3, 3), dtype=int))
        for k in range(1, n + 1):
            if len(segments) >= max_segments:
                break
            ii, jj = np.nonzero(labels == k)
            if len(ii) < min_segment_px:
                continue
            p0, p1 = _endpoints(x[ii], y[jj], dx, dy)
            segments.append((family, p0, p1))
    return Segments(mag, edges, threshold, sigma, families, tuple(segments))


def detect_transitions(
    record: MeasurementRecord,
    payload: Payload,
    *,
    variable: str = "",
    smooth_px: float = 1.0,
    threshold_rel: float = 0.3,
    threshold_noise: float = 5.0,
    min_separation_deg: float = 15.0,
    window_deg: float = 12.0,
    min_segment_px: int = 6,
    max_segments: int = 200,
    min_periods: float = 5.0,
    zero_pad: int = 4,
) -> AnalysisResult:
    """Detect transition segments and estimate the charge lattice of a 2-D map.

    `variable` defaults to the first data variable whose last two dims carry linear coordinates. Leading
    dims (repeat, shot) are averaged over, ignoring NaN. Raises ValueError when no such variable exists
    or `record` is not the payload's record.
    """
    method = FitModel(
        name=NAME,
        version=VERSION,
        parameters={
            "variable": variable,
            "smooth_px": smooth_px,
            "threshold_rel": threshold_rel,
            "threshold_noise": threshold_noise,
            "min_separation_deg": min_separation_deg,
            "window_deg": window_deg,
            "min_segment_px": min_segment_px,
            "max_segments": max_segments,
            "min_periods": min_periods,
            "zero_pad": zero_pad,
        },
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
    dx = (x[-1] - x[0]) / (len(x) - 1) if len(x) > 1 else 0.0
    dy = (y[-1] - y[0]) / (len(y) - 1) if len(y) > 1 else 0.0
    result_id = uuid.uuid4().hex

    def done(status, message="", estimates=(), annotations=(), **attrs):
        return AnalysisResult(
            result_id=result_id,
            record_id=record.record_id,
            dataset_id=dataset.dataset_id,
            method=method,
            method_sha256=method.content_sha256(),
            status=status,
            message=message,
            estimates=tuple(estimates),
            annotations=tuple(annotations),
            created_at=datetime.now(UTC),
            attrs={"variable": var.name, **attrs},
        )

    if min(image.shape) < 16 or dx == 0 or dy == 0:
        return done("failed", "map smaller than 16 × 16 points")
    finite = np.isfinite(image)
    if finite.mean() < 0.5:
        return done("failed", "fewer than half the points are finite")
    image = np.where(finite, image, np.nanmedian(image))

    # 1. detect
    found = detect_segments(
        image,
        x,
        y,
        smooth_px=smooth_px,
        threshold_rel=threshold_rel,
        threshold_noise=threshold_noise,
        min_separation_deg=min_separation_deg,
        window_deg=window_deg,
        min_segment_px=min_segment_px,
        max_segments=max_segments,
    )
    n_edges = int(found.edges.sum())
    if n_edges < 20:
        return done("failed", f"only {n_edges} transition pixels found", n_edge_pixels=n_edges)

    # 2. estimate the lattice from the gradient-magnitude spectrum
    lattice = _lattice(found.magnitude, dx, dy, min_periods, zero_pad)
    if lattice is None:
        return done("failed", "no two non-collinear lattice peaks", n_edge_pixels=n_edges)
    a, b = lattice  # electrons per volt on the dot dominated by the row gate (a) / column gate (b)
    unit = f"1/{row.unit}" if row.unit == col.unit and row.unit else ""
    estimates = [
        Estimate(name="a_per_volt_row", value=a[0], unit=unit),
        Estimate(name="a_per_volt_col", value=a[1], unit=unit),
        Estimate(name="b_per_volt_row", value=b[0], unit=unit),
        Estimate(name="b_per_volt_col", value=b[1], unit=unit),
        Estimate(name="cross_ratio_a", value=a[1] / a[0], unit=""),
        Estimate(name="cross_ratio_b", value=b[0] / b[1], unit=""),
    ]

    # 3. overlays: segments of the two gradient-direction families
    annotations = [
        Annotation(
            annotation_id=f"{result_id[:12]}-{family}-{k}",
            dataset_id=dataset.dataset_id,
            kind="line",
            coords=(row.name, col.name),
            points=(p0, p1),
            attrs={"family": family},
        )
        for k, (family, p0, p1) in enumerate(found.segments)
    ]
    return done(
        "ok",
        estimates=estimates,
        annotations=annotations,
        n_edge_pixels=n_edges,
        threshold=found.threshold,
        noise=found.noise,
    )


def _lattice(mag, dx, dy, min_periods, pad):
    """Reciprocal lattice rows (a, b) in 1/V from the power spectrum of `mag`, or None.

    `a` is the vector dominated by its row component, `b` by its column component, each signed so the
    dominant component is positive.
    """
    n0, n1 = mag.shape
    window = np.outer(np.hanning(n0), np.hanning(n1))
    spec = (
        np.abs(np.fft.fftshift(np.fft.fft2((mag - mag.mean()) * window, s=(pad * n0, pad * n1))))
        ** 2
    )
    kx = np.fft.fftshift(np.fft.fftfreq(pad * n0, dx))
    ky = np.fft.fftshift(np.fft.fftfreq(pad * n1, dy))
    kxx, kyy = np.meshgrid(kx, ky, indexing="ij")
    spec[np.hypot(kxx, kyy) < min_periods / min(n0 * abs(dx), n1 * abs(dy))] = 0.0
    if spec.max() <= 0:
        return None
    peaks = (spec == maximum_filter(spec, size=2 * pad + 1)) & (spec > 0.05 * spec.max())
    found = []
    for i, j in np.argwhere(peaks):
        if not (0 < i < spec.shape[0] - 1 and 0 < j < spec.shape[1] - 1):
            continue
        if kxx[i, j] < 0 or (kxx[i, j] == 0 and kyy[i, j] < 0):
            continue  # each peak appears twice (±k); keep one
        di = _vertex(spec[i - 1, j], spec[i, j], spec[i + 1, j])
        dj = _vertex(spec[i, j - 1], spec[i, j], spec[i, j + 1])
        found.append(
            np.array([kx[0] + (i + di) * (kx[1] - kx[0]), ky[0] + (j + dj) * (ky[1] - ky[0])])
        )
    found.sort(key=lambda k: float(np.hypot(*k)))
    if len(found) < 2:
        return None
    first = found[0]
    for other in found[1:]:
        sin = abs(first[0] * other[1] - first[1] * other[0]) / (np.hypot(*first) * np.hypot(*other))
        if sin > math.sin(math.radians(20)):
            break
    else:
        return None
    vecs = [v if v[int(np.argmax(np.abs(v)))] > 0 else -v for v in (first, other)]
    vecs.sort(key=lambda v: -abs(v[0]) / np.hypot(*v))  # row-dominant first
    return tuple(tuple(float(c) for c in v) for v in vecs)


def _vertex(a, b, c):
    """Sub-bin offset of a parabola through log-powers a, b (peak), c; 0 when degenerate."""
    la, lb, lc = (math.log(max(v, 1e-300)) for v in (a, b, c))
    den = la - 2 * lb + lc
    return max(-0.5, min(0.5, 0.5 * (la - lc) / den)) if den < 0 else 0.0


def _families(theta, weights, min_separation_deg):
    """[(label, normal angle)] of the two strongest gradient-direction peaks: 'steep' and 'shallow'
    by the slope of the lines they belong to."""
    bins = 180
    hist, _ = np.histogram(theta, bins=bins, range=(0, np.pi), weights=weights)
    hist = gaussian_filter1d(hist, 2.0, mode="wrap")
    centers = (np.arange(bins) + 0.5) * np.pi / bins
    first = int(np.argmax(hist))
    sep = np.abs(np.angle(np.exp(2j * (centers - centers[first])))) / 2
    masked = np.where(sep >= math.radians(min_separation_deg), hist, -np.inf)
    second = int(np.argmax(masked))
    normals = [centers[first]] + ([centers[second]] if np.isfinite(masked[second]) else [])
    # a line with normal angle t has slope -cot t; |cot| large means steep
    normals.sort(key=lambda t: -abs(math.cos(t) / max(abs(math.sin(t)), 1e-12)))
    return list(zip(("steep", "shallow"), normals, strict=False))


def _ridge(mag, g_r, g_c):
    """Non-maximum suppression: True where `mag` is a local maximum across the edge (along the gradient,
    quantised to 8 directions), so each transition becomes a one-pixel-wide line."""
    angle = np.mod(np.rad2deg(np.arctan2(g_c, g_r)), 180.0)
    q = (np.rint(angle / 45.0).astype(int)) % 4  # 0: rows, 1: diagonal, 2: cols, 3: anti-diagonal
    p = np.pad(mag, 1, mode="edge")
    c = p[1:-1, 1:-1]
    neighbours = {
        0: (p[:-2, 1:-1], p[2:, 1:-1]),
        1: (p[:-2, :-2], p[2:, 2:]),
        2: (p[1:-1, :-2], p[1:-1, 2:]),
        3: (p[:-2, 2:], p[2:, :-2]),
    }
    keep = np.zeros(mag.shape, dtype=bool)
    for k, (a, b) in neighbours.items():
        keep |= (q == k) & (c >= a) & (c >= b)
    return keep


def _endpoints(sx, sy, dx, dy):
    """Segment ends: extreme projections onto its principal axis (in pixel units), through its centroid."""
    u, v = (sx - sx.mean()) / dx, (sy - sy.mean()) / dy
    _, evecs = np.linalg.eigh(np.cov(np.vstack([u, v])))
    du, dv = evecs[:, 1]
    proj = u * du + v * dv
    cx, cy = float(sx.mean()), float(sy.mean())
    lo, hi = float(proj.min()), float(proj.max())
    return (cx + lo * du * dx, cy + lo * dv * dy), (cx + hi * du * dx, cy + hi * dv * dy)


def _derivative_gain(smooth_px: float) -> float:
    """Std of one component of the smoothed gradient for unit white noise, per pixel."""
    delta = np.zeros(int(8 * smooth_px) * 2 + 1)
    delta[len(delta) // 2] = 1.0
    d = gaussian_filter1d(delta, smooth_px, order=1)
    g = gaussian_filter1d(delta, smooth_px)
    return float(np.sqrt(np.sum(d**2) * np.sum(g**2)))


def _pick(payload: Payload, variable: str):
    """(variable, row coordinate, column coordinate) to analyse."""
    dataset = payload.dataset
    linear = {c.dim: c for c in dataset.coords if isinstance(c, LinearCoordinate)}
    candidates = [
        v for v in dataset.data_vars if len(v.dims) >= 2 and all(d in linear for d in v.dims[-2:])
    ]
    if variable:
        candidates = [v for v in candidates if v.name == variable]
    if not candidates:
        what = f"data variable {variable!r}" if variable else "data variable"
        raise ValueError(f"no {what} with linear coordinates on its last two dims")
    v = candidates[0]
    return v, linear[v.dims[-2]], linear[v.dims[-1]]
