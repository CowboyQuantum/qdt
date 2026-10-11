"""Regenerate the committed replay fixtures in packages/qdt-lab/tests/fixtures/stream/.

Run only when the wire format or the synthetic sources change: `uv run python scripts/make_stream_fixtures.py`.
Recordings embed wall-clock timestamps, so bytes differ per run; tests compare content, not bytes.
"""

import pathlib

from qdt_lab.stream import SyntheticMap, SyntheticRecords, write_recording
from qdt_schemas.data import Annotation

OUT = pathlib.Path(__file__).resolve().parents[1] / "packages/qdt-lab/tests/fixtures/stream"

# Kept here so tests can rebuild the same sources and compare content.
MAP = {"n_outer": 64, "n_inner": 64, "seed": 7, "dataset_id": "fixture-map-64"}
RECORDS = {"n_samples": 500, "n_records": 8, "seed": 7, "dataset_id": "fixture-records-8"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # paced at 10^5 pts/s so recorded produced_at stamps carry realistic spacing for paced replay
    m = SyntheticMap(**MAP, points_per_second=100_000)
    transition = Annotation(
        annotation_id="transition-0",
        dataset_id=MAP["dataset_id"],
        kind="line",
        coords=("V_inner", "V_outer"),
        points=((-1 / 12, 0.5), (0.25, -0.5)),  # along 6*V_inner + 2*V_outer = 0.5, a peak ridge
        label="example transition line",
    )
    write_recording(OUT / "synthetic_map_64.qdtrec", m, [transition])
    r = SyntheticRecords(**RECORDS, records_per_second=50.0)
    write_recording(OUT / "synthetic_records_8.qdtrec", r)
    for p in sorted(OUT.glob("*.qdtrec")):
        print(f"{p.relative_to(OUT.parents[3])}: {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
