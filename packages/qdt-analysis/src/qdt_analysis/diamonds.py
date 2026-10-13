"""Coulomb diamonds on a (gate, bias) map: detect the edges, estimate the diamond parameters (ADR 0030).

Detection and estimation are separate stages:

1. **Detect** the diamond edges with `transitions.detect_segments`: they are the ridges of the current's
   gradient, in two gradient-direction families (edges rising and falling with the gate). Each run is a
   straight segment and a `line` overlay.
2. **Estimate** the diamonds. Every edge, as a line `bias = slope · (gate − crossing)`, crosses zero bias
   at a degeneracy point. Crossings of both families cluster into the degeneracy points (markers), whose
   mean spacing is the period. The median slope of each family gives the edge directions. The apex of a
   diamond is where the rising edge of one degeneracy point meets the falling edge of the next; with
   symmetric leads its bias is the charging energy (`E_c = e · V_apex`, so eV for V), and the lever arm
   is `E_c / period`. Each complete diamond is a `region` overlay.

Rows of the map are the gate, columns the bias. Pure: schema objects in, `Analysis` (result plus the
detection map as an in-memory output payload, ADR 0031) out (rule 5).
"""

import itertools
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from qdt_schemas.data import Annotation
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.modeling import AnalysisResult, Estimate, FitModel
from qdt_schemas.payload_hdf5 import Payload

from .transitions import Analysis, _pick, detect_segments, detection_map

NAME = "qdt_analysis.diamonds.detect_diamonds"
VERSION = "1"


@dataclass(frozen=True)
class Edge:
    """One diamond edge as a line in data coordinates: `bias = slope · (gate − crossing)`."""

    family: str
    start: tuple[float, float]
    """(gate, bias) of one end of the detected run."""
    stop: tuple[float, float]
    slope: float
    """d bias / d gate (V/V)."""
    crossing: float
    """Gate value where the line crosses zero bias."""


@dataclass(frozen=True)
class Diamonds:
    """The estimation stage's output."""

    edges: tuple[Edge, ...]
    points: tuple[float, ...]
    """Degeneracy points (gate values at zero bias), ascending."""
    slope_rising: float
    slope_falling: float
    period: float
    """Mean spacing of the degeneracy points (gate units); NaN with fewer than two points."""
    apexes: tuple[tuple[float, float, float], ...]
    """Per complete diamond: (gate of the apex, positive apex bias, negative apex bias)."""
    charging_energy: float
    """e · mean apex bias (eV for biases in V); NaN without a complete diamond."""


def estimate_diamonds(
    segments: tuple[tuple[str, tuple[float, float], tuple[float, float]], ...],
    gate_pitch: float,
    *,
    point_tolerance_px: float = 3.0,
) -> Diamonds:
    """Stage 2 from detected segments in (gate, bias) data coordinates.

    Each family's slope is the length-weighted median of its segments' slopes; a segment's zero-bias
    crossing is then extrapolated through its midpoint with the family slope, not its own (a short
    fragment's slope is noisy, and the extrapolation from the apex region is long). Degeneracy points are
    length-weighted cluster means of the crossings.
    """
    raw = []
    for family, (g0, b0), (g1, b1) in segments:
        if abs(g1 - g0) < 1e-12 * max(1.0, abs(g0)):
            continue  # a vertical edge has no zero-bias crossing: not a diamond edge
        raw.append((family, (g0, b0), (g1, b1), (b1 - b0) / (g1 - g0), math.hypot(g1 - g0, b1 - b0)))

    def family_slope(sign: int) -> float:
        members = [(s, w) for _, _, _, s, w in raw if sign * s > 0]
        if not members:
            return math.nan
        slopes, weights = zip(*sorted(members), strict=True)
        half = 0.5 * sum(weights)
        return float(next(s for s, c in zip(slopes, np.cumsum(weights), strict=True) if c >= half))

    s_up, s_down = family_slope(+1), family_slope(-1)
    edges, weights = [], []
    for family, start, stop, slope, length in raw:
        s = s_up if slope > 0 else s_down
        g_mid, b_mid = (start[0] + stop[0]) / 2, (start[1] + stop[1]) / 2
        edges.append(Edge(family, start, stop, slope, g_mid - b_mid / s))
        weights.append(length)
    rising = [e for e in edges if e.slope > 0]
    falling = [e for e in edges if e.slope < 0]
    order = np.argsort([e.crossing for e in edges])
    crossings = np.array([edges[i].crossing for i in order])
    w = np.array([weights[i] for i in order])
    points, start = [], 0
    for k in range(1, len(crossings) + 1):
        if k == len(crossings) or crossings[k] - crossings[k - 1] > point_tolerance_px * abs(gate_pitch):
            points.append(float(np.average(crossings[start:k], weights=w[start:k])))
            start = k
    points = tuple(points)
    period = float(np.mean(np.diff(points))) if len(points) > 1 else math.nan
    apexes = []
    if len(points) > 1 and rising and falling:
        for g_k, g_next in itertools.pairwise(points):
            x = (s_up * g_k - s_down * g_next) / (s_up - s_down)
            top = s_up * (x - g_k)
            x_bottom = (s_down * g_k - s_up * g_next) / (s_down - s_up)
            bottom = s_down * (x_bottom - g_k)
            apexes.append((float(x), float(top), float(bottom)))
    e_c = float(np.mean([(t - b) / 2 for _, t, b in apexes])) if apexes else math.nan
    return Diamonds(tuple(edges), points, s_up, s_down, period, tuple(apexes), e_c)


def detect_diamonds(
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
    point_tolerance_px: float = 3.0,
) -> Analysis:
    """Detect Coulomb-diamond edges on a (gate, bias) map and estimate period, charging energy, lever
    arm and edge slopes. The output is the detection map (ADR 0031).

    `variable` defaults to the first data variable whose last two dims carry linear coordinates; the
    row coordinate is the gate, the column coordinate the bias. Raises ValueError when no such variable
    exists or `record` is not the payload's record. Returns `status="failed"` when fewer than two
    degeneracy points or no complete diamond is found.
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
            "point_tolerance_px": point_tolerance_px,
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
    gate = np.linspace(row.start, row.stop, row.num)
    bias = np.linspace(col.start, col.stop, col.num)
    result_id = uuid.uuid4().hex
    now = datetime.now(UTC)
    found = None

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
            detection_map(
                result_id, "diamond detection map", dataset, row, col, found, list(annotations), now
            )
            if found is not None
            else None
        )
        return Analysis(result, output)

    if min(image.shape) < 16 or gate.size < 2 or bias.size < 2:
        return done("failed", "map smaller than 16 × 16 points")
    finite = np.isfinite(image)
    if finite.mean() < 0.5:
        return done("failed", "fewer than half the points are finite")
    image = np.where(finite, image, np.nanmedian(image))

    found = detect_segments(
        image,
        gate,
        bias,
        smooth_px=smooth_px,
        threshold_rel=threshold_rel,
        threshold_noise=threshold_noise,
        min_separation_deg=min_separation_deg,
        window_deg=window_deg,
        min_segment_px=min_segment_px,
        max_segments=max_segments,
        family_space="pixel",  # a bias axis spans millivolts: voltage-space normals coincide
    )
    n_edges = int(found.edges.sum())
    if n_edges < 20:
        return done("failed", f"only {n_edges} edge pixels found", n_edge_pixels=n_edges)
    d = estimate_diamonds(
        found.segments, gate[1] - gate[0], point_tolerance_px=point_tolerance_px
    )
    coords = (row.name, col.name)
    annotations: list[Annotation] = [
        Annotation(
            annotation_id=f"{result_id[:12]}-edge-{k}",
            dataset_id=dataset.dataset_id,
            kind="line",
            coords=coords,
            points=(e.start, e.stop),
            attrs={"family": e.family, "slope": e.slope, "crossing": e.crossing},
        )
        for k, e in enumerate(d.edges)
    ]
    annotations += [
        Annotation(
            annotation_id=f"{result_id[:12]}-point-{k}",
            dataset_id=dataset.dataset_id,
            kind="marker",
            coords=coords,
            points=((g, 0.0),),
            label=f"g{k}",
        )
        for k, g in enumerate(d.points)
    ]
    if len(d.points) < 2 or not d.apexes:
        return done(
            "failed",
            f"{len(d.points)} degeneracy point(s) and {len(d.edges)} edge(s): no complete diamond",
            annotations=annotations,
            n_edge_pixels=n_edges,
        )
    annotations += [
        Annotation(
            annotation_id=f"{result_id[:12]}-diamond-{k}",
            dataset_id=dataset.dataset_id,
            kind="region",
            coords=coords,
            points=((d.points[k], 0.0), (x, top), (d.points[k + 1], 0.0), (x, bottom)),
            label=f"E_c {top * 1e3:.2f} meV",
            attrs={"apex_bias": top, "apex_bias_negative": bottom},
        )
        for k, (x, top, bottom) in enumerate(d.apexes)
    ]
    gate_unit, bias_unit = row.unit, col.unit
    estimates = [
        Estimate(name="period", value=d.period, unit=gate_unit),
        Estimate(name="charging_energy", value=d.charging_energy, unit="eV" if bias_unit == "V" else ""),
        Estimate(
            name="lever_arm",
            value=d.charging_energy / d.period,
            unit=f"eV/{gate_unit}" if bias_unit == "V" and gate_unit else "",
        ),
        Estimate(
            name="slope_rising",
            value=d.slope_rising,
            unit=f"{bias_unit}/{gate_unit}" if gate_unit and bias_unit else "",
        ),
        Estimate(
            name="slope_falling",
            value=d.slope_falling,
            unit=f"{bias_unit}/{gate_unit}" if gate_unit and bias_unit else "",
        ),
    ]
    return done(
        "ok",
        estimates=estimates,
        annotations=annotations,
        n_edge_pixels=n_edges,
        n_edges=len(d.edges),
        n_points=len(d.points),
        n_diamonds=len(d.apexes),
        threshold=found.threshold,
        noise=found.noise,
    )
