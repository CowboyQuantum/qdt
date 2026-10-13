"""Coulomb diamonds on a (gate, bias) map: detection reused from `transitions`, estimation here (ADR 0031).

Detection: the diamond edges are the ridges of the current's gradient, in two orientation families
(edges rising and falling with the gate), so `transitions.detect` / `transitions.estimate` find them
as straight segments.

Estimation: every edge, as a line in data coordinates `V_sd = s · (V_g − g)`, crosses zero bias at a
degeneracy point `g`. Clustering the crossings of both families gives the degeneracy points and the
period; the median slopes give the two edge directions; the apex of a diamond is where the rising edge
of one degeneracy point meets the falling edge of the next, and its bias is the charging energy
(`E_c = e · V_apex`, symmetric leads). The lever arm follows as `E_c / period`.

Annotations: the edges (lines), the degeneracy points (markers) and each complete diamond (region) in the
Dataset's coordinates. Pure functions throughout (rule 5).
"""

import itertools
import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from qdt_schemas.data import Annotation, Dataset
from qdt_schemas.modeling import AnalysisResult, FitModel, MeasurementRef, ScenarioRef

from . import __version__
from .transitions import DEFAULTS as DETECTOR_DEFAULTS
from .transitions import Segment, axis_values, detect, estimate, map_of

MODEL_NAME = "coulomb_diamonds"

DEFAULTS: dict[str, float | int] = {**DETECTOR_DEFAULTS, "point_tolerance_px": 3.0}
"""`transitions.DEFAULTS` for the edge detection, plus:

point_tolerance_px: zero-bias crossings closer than this (in gate pixels) are one degeneracy point.
"""


@dataclass(frozen=True)
class Edge:
    """One diamond edge as a line in data coordinates: `bias = slope · (gate − crossing)`."""

    segment: Segment
    start: tuple[float, float]
    """(gate, bias) of one end of the detected run."""
    stop: tuple[float, float]
    slope: float
    """d bias / d gate (V/V)."""
    crossing: float
    """Gate value where the line crosses zero bias."""


@dataclass(frozen=True)
class Diamonds:
    """Stage 2 output."""

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


def _edges(segments: list[Segment], gate: np.ndarray, bias: np.ndarray) -> list[Edge]:
    def to_data(p: tuple[float, float]) -> tuple[float, float]:
        return (
            float(np.interp(p[0], np.arange(gate.size), gate)),
            float(np.interp(p[1], np.arange(bias.size), bias)),
        )

    out = []
    for s in segments:
        (g0, b0), (g1, b1) = to_data(s.start), to_data(s.stop)
        if abs(g1 - g0) < 1e-12 * max(1.0, abs(g0)):
            continue  # a vertical edge has no zero-bias crossing: not a diamond edge
        slope = (b1 - b0) / (g1 - g0)
        out.append(Edge(s, (g0, b0), (g1, b1), slope, g0 - b0 / slope))
    return out


def _cluster(values: np.ndarray, tolerance: float) -> list[np.ndarray]:
    if values.size == 0:
        return []
    order = np.sort(values)
    groups, current = [], [order[0]]
    for v in order[1:]:
        if v - current[-1] <= tolerance:
            current.append(v)
        else:
            groups.append(np.array(current))
            current = [v]
    groups.append(np.array(current))
    return groups


def estimate_diamonds(
    segments: list[Segment], gate: np.ndarray, bias: np.ndarray, *, point_tolerance_px: float
) -> Diamonds:
    """Stage 2: lines, degeneracy points, period, slopes, apexes and charging energy."""
    edges = _edges(segments, gate, bias)
    rising = [e for e in edges if e.slope > 0]
    falling = [e for e in edges if e.slope < 0]
    pitch = abs(gate[-1] - gate[0]) / max(gate.size - 1, 1)
    clusters = _cluster(np.array([e.crossing for e in edges]), point_tolerance_px * pitch)
    points = tuple(float(c.mean()) for c in clusters)
    s_up = float(np.median([e.slope for e in rising])) if rising else math.nan
    s_down = float(np.median([e.slope for e in falling])) if falling else math.nan
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


def coulomb_diamonds(
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
    """Detect Coulomb-diamond edges on `dataset`'s (gate, bias) map and estimate the diamond parameters.

    Rows of the map are the gate, columns the bias. Returns the edges as line annotations, the
    degeneracy points as markers, each complete diamond as a region, and in `summary` the period,
    charging energy (eV), lever arm (eV/V) and edge slopes.
    """
    unknown = set(parameters) - set(DEFAULTS)
    if unknown:
        raise TypeError(f"unknown diamond parameters {sorted(unknown)}; see DEFAULTS")
    params: dict[str, float | int] = {**DEFAULTS, **parameters}
    name, z, (gate_dim, bias_dim) = map_of(dataset, arrays, variable)
    merging = {"merge_tolerance", "merge_gap"}
    detector = {k: v for k, v in params.items() if k in DETECTOR_DEFAULTS and k not in merging}
    detection = detect(z, **detector)
    segments = estimate(detection, **{k: params[k] for k in merging})
    gate_name, gate = axis_values(dataset, arrays, gate_dim)
    bias_name, bias = axis_values(dataset, arrays, bias_dim)
    d = estimate_diamonds(segments, gate, bias, point_tolerance_px=params["point_tolerance_px"])
    analysis_id = analysis_id or uuid.uuid4().hex
    coords = (gate_name, bias_name)
    annotations: list[Annotation] = []
    for k, e in enumerate(d.edges):
        annotations.append(
            Annotation(
                annotation_id=f"{analysis_id}:edge:{k}",
                dataset_id=dataset.dataset_id,
                kind="line",
                coords=coords,
                points=(e.start, e.stop),
                label="",
                attrs={
                    "slope": e.slope,
                    "crossing": e.crossing,
                    "strength": e.segment.strength,
                    "n_pixels": e.segment.n_pixels,
                },
            )
        )
    for k, g in enumerate(d.points):
        annotations.append(
            Annotation(
                annotation_id=f"{analysis_id}:point:{k}",
                dataset_id=dataset.dataset_id,
                kind="marker",
                coords=coords,
                points=((g, 0.0),),
                label=f"g{k}",
            )
        )
    for k, (x, top, bottom) in enumerate(d.apexes):
        annotations.append(
            Annotation(
                annotation_id=f"{analysis_id}:diamond:{k}",
                dataset_id=dataset.dataset_id,
                kind="region",
                coords=coords,
                points=((d.points[k], 0.0), (x, top), (d.points[k + 1], 0.0), (x, bottom)),
                label=f"E_c {top * 1e3:.2f} meV" if math.isfinite(top) else "",
                attrs={"apex_bias": top, "apex_bias_negative": bottom},
            )
        )
    summary: dict[str, float | int] = {
        "n_edges": len(d.edges),
        "n_points": len(d.points),
        "n_diamonds": len(d.apexes),
        "period_v": d.period,
        "charging_energy_ev": d.charging_energy,
        "lever_arm_ev_per_v": d.charging_energy / d.period if d.period else math.nan,
        "slope_rising": d.slope_rising,
        "slope_falling": d.slope_falling,
    }
    summary = {k: v for k, v in summary.items() if not (isinstance(v, float) and math.isnan(v))}
    return AnalysisResult(
        analysis_id=analysis_id,
        model=FitModel(name=MODEL_NAME, version=__version__, parameters=params),
        measurement=MeasurementRef(dataset_id=dataset.dataset_id, variable=name, record_id=record_id),
        scenario=scenario,
        annotations=tuple(annotations),
        summary=summary,
        created_at=created_at or datetime.now(UTC),
    )
