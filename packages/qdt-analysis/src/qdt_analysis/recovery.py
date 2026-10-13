"""Injection–recovery: score detected lines against a known truth mask, in pixels.

The truth comes from the scenario that generated the data (a `qdt_sim` model's `transition_map`, or
the lines a synthetic generator injected); the detections come from an `AnalysisResult`. Both are
compared on the map's pixel grid: precision is the fraction of detected line length within `tolerance`
pixels of a truth pixel, recall the fraction of truth pixels within `tolerance` of a detected line.
"""

from collections.abc import Mapping
from typing import NamedTuple

import numpy as np
from scipy import ndimage

from qdt_schemas.data import Annotation, Dataset
from qdt_schemas.modeling import AnalysisResult

from .transitions import axis_values


class Recovery(NamedTuple):
    """Scores in [0, 1]; `n_detected` and `n_truth` are pixel counts behind them."""

    precision: float
    recall: float
    n_detected: int
    n_truth: int


def line_pixels(dataset: Dataset, arrays: Mapping[str, np.ndarray], line: Annotation) -> np.ndarray:
    """A line annotation's endpoints as fractional (row, col) pixel indices, shape (2, 2)."""
    if line.kind != "line":
        raise ValueError(f"annotation {line.annotation_id!r} is a {line.kind}, not a line")
    row_dim = next(c.dim for c in dataset.coords if c.name == line.coords[0])
    col_dim = next(c.dim for c in dataset.coords if c.name == line.coords[1])
    _, rows = axis_values(dataset, arrays, row_dim)
    _, cols = axis_values(dataset, arrays, col_dim)
    return np.array(
        [
            (np.interp(p[0], rows, np.arange(rows.size)), np.interp(p[1], cols, np.arange(cols.size)))
            for p in line.points
        ]
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
    to_truth = ndimage.distance_transform_edt(~truth) if n_truth else np.full(truth.shape, np.inf)
    to_detected = (
        ndimage.distance_transform_edt(~detected) if n_detected else np.full(truth.shape, np.inf)
    )
    precision = float((to_truth[detected] <= tolerance).mean()) if n_detected else 0.0
    recall = float((to_detected[truth] <= tolerance).mean()) if n_truth else 0.0
    return Recovery(precision, recall, n_detected, n_truth)


def recovery(
    result: AnalysisResult,
    dataset: Dataset,
    arrays: Mapping[str, np.ndarray],
    truth: np.ndarray,
    *,
    tolerance: float = 1.5,
) -> Recovery:
    """Score a result's line annotations against a truth mask on the analysed variable's grid."""
    segments = np.array(
        [line_pixels(dataset, arrays, a) for a in result.annotations if a.kind == "line"]
    ).reshape(-1, 2, 2)
    return score(rasterize(segments, truth.shape), truth.astype(bool), tolerance)
