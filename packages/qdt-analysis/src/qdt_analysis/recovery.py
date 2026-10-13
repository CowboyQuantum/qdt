"""Injection–recovery scoring of line overlays against a known truth mask, in pixels.

The truth comes from whatever generated the data (a `qdt_sim` model's `diamond_edges`, or the lines a
synthetic generator injected); the detections are a result's `line` annotations. Both are compared on
the map's pixel grid: precision is the fraction of detected line length within `tolerance` pixels of a
truth pixel, recall the fraction of truth pixels within `tolerance` of a detected line. Pure (rule 5).
"""

from typing import NamedTuple

import numpy as np
from scipy.ndimage import distance_transform_edt

from qdt_schemas.data import Annotation, Dataset, LinearCoordinate
from qdt_schemas.modeling import AnalysisResult


class Recovery(NamedTuple):
    """Scores in [0, 1]; `n_detected` and `n_truth` are the pixel counts behind them."""

    precision: float
    recall: float
    n_detected: int
    n_truth: int


def line_pixels(dataset: Dataset, line: Annotation) -> np.ndarray:
    """A line annotation's endpoints as fractional (row, col) pixel indices, shape (2, 2); the
    annotation's coordinates must be linear."""
    if line.kind != "line":
        raise ValueError(f"annotation {line.annotation_id!r} is a {line.kind}, not a line")
    axes = []
    for name in line.coords:
        c = next(c for c in dataset.coords if c.name == name)
        if not isinstance(c, LinearCoordinate):
            raise TypeError(f"coordinate {name!r} is not linear")
        axes.append(np.linspace(c.start, c.stop, c.num))
    return np.array(
        [[np.interp(v, axis, np.arange(axis.size)) for v, axis in zip(p, axes, strict=True)] for p in line.points]
    )


def rasterize(segments: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Boolean mask of `shape` with every (2, 2) pixel-space segment drawn one pixel wide."""
    out = np.zeros(shape, dtype=bool)
    for (r0, c0), (r1, c1) in segments:
        n = int(np.ceil(2 * max(abs(r1 - r0), abs(c1 - c0)))) + 1
        r = np.rint(np.linspace(r0, r1, n)).astype(int)
        c = np.rint(np.linspace(c0, c1, n)).astype(int)
        keep = (r >= 0) & (r < shape[0]) & (c >= 0) & (c < shape[1])
        out[r[keep], c[keep]] = True
    return out


def score(detected: np.ndarray, truth: np.ndarray, tolerance: float) -> Recovery:
    """Precision/recall of two boolean masks with a distance tolerance in pixels."""
    if detected.shape != truth.shape:
        raise ValueError("detected and truth masks differ in shape")
    n_detected, n_truth = int(detected.sum()), int(truth.sum())
    to_truth = distance_transform_edt(~truth) if n_truth else np.full(truth.shape, np.inf)
    to_detected = distance_transform_edt(~detected) if n_detected else np.full(truth.shape, np.inf)
    precision = float((to_truth[detected] <= tolerance).mean()) if n_detected else 0.0
    recall = float((to_detected[truth] <= tolerance).mean()) if n_truth else 0.0
    return Recovery(precision, recall, n_detected, n_truth)


def recovery(
    result: AnalysisResult, dataset: Dataset, truth: np.ndarray, *, tolerance: float = 1.5
) -> Recovery:
    """Score a result's line annotations against a truth mask on the analysed map's pixel grid."""
    segments = np.array(
        [line_pixels(dataset, a) for a in result.annotations if a.kind == "line"]
    ).reshape(-1, 2, 2)
    return score(rasterize(segments, truth.shape), truth.astype(bool), tolerance)
