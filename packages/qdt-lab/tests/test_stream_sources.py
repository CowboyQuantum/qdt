"""Replay over committed recordings, and source equivalence: the same Dataset through the synthetic
source directly, through a replay recording, and through the live WebSocket server assembles identically.
"""

import asyncio
import time
from pathlib import Path

import numpy as np
import pytest

from qdt_lab.stream import (
    ReplaySource,
    Source,
    StreamServer,
    SyntheticMap,
    SyntheticRecords,
    assemble,
    collect,
    read_recording,
    write_recording,
)
from qdt_schemas.data import Annotation

FIXTURES = Path(__file__).parent / "fixtures" / "stream"
# Must match scripts/make_stream_fixtures.py, which regenerates the recordings.
MAP = {"n_outer": 64, "n_inner": 64, "seed": 7, "dataset_id": "fixture-map-64"}
RECORDS = {"n_samples": 500, "n_records": 8, "seed": 7, "dataset_id": "fixture-records-8"}


def fixture_pairs():
    return [
        pytest.param(
            FIXTURES / "synthetic_map_64.qdtrec",
            lambda: SyntheticMap(**MAP, points_per_second=None),
            id="map",
        ),
        pytest.param(
            FIXTURES / "synthetic_records_8.qdtrec",
            lambda: SyntheticRecords(**RECORDS, records_per_second=None),
            id="records",
        ),
    ]


def assert_same(a, b):
    assert a.equals(b), f"assembled datasets differ:\n{a}\n---\n{b}"


def live(source: Source, annotations=()) -> tuple:
    async def run():
        async with StreamServer() as server:
            feeding = asyncio.create_task(server.feed(source))
            await asyncio.sleep(0)  # let feed() announce the dataset
            for ann in annotations:
                server.publish_annotation(ann)
            got = await collect(server.url)
            await feeding
            return got[source.dataset.dataset_id]

    return asyncio.run(run())


@pytest.mark.parametrize(("path", "make"), fixture_pairs())
def test_committed_recording_replays_to_the_synthetic_content(path, make):
    replay = ReplaySource(path)
    synthetic = make()
    assert replay.dataset.model_dump(exclude={"created_at"}) == synthetic.dataset.model_dump(
        exclude={"created_at"}
    )
    assert_same(
        assemble(replay.dataset, replay.frames()), assemble(synthetic.dataset, synthetic.frames())
    )


def test_recording_carries_annotations():
    replay = ReplaySource(FIXTURES / "synthetic_map_64.qdtrec")
    assert [a.annotation_id for a in replay.annotations] == ["transition-0"]


@pytest.mark.parametrize(("path", "make"), fixture_pairs())
def test_source_equivalence_synthetic_replay_live(path, make):
    direct = assemble(make().dataset, make().frames())
    replay = ReplaySource(path)
    replayed = assemble(replay.dataset, replay.frames())
    received = live(make())
    over_wire = assemble(received.dataset, received.frames)
    assert_same(direct, replayed)
    assert_same(direct, over_wire)


def test_live_stream_carries_annotations_in_order():
    src = SyntheticMap(n_outer=4, n_inner=8, points_per_second=None, dataset_id="ann")
    ann = Annotation(
        annotation_id="m", dataset_id="ann", kind="marker", coords=("V_inner",), points=((0.1,),)
    )
    received = live(src, [ann])
    assert received.annotations == [ann]
    assert [f.chunk.seq for f in received.frames] == list(range(4))


def test_late_client_receives_full_history():
    async def run():
        async with StreamServer() as server:
            src = SyntheticMap(n_outer=8, n_inner=16, points_per_second=None)
            await server.feed(src)  # source finished before anyone connects
            first, second = await asyncio.gather(collect(server.url), collect(server.url))
            return src, first, second

    src, first, second = asyncio.run(run())
    expected = assemble(src.dataset, src.frames())
    for got in (first, second):
        r = got[src.dataset.dataset_id]
        assert_same(expected, assemble(r.dataset, r.frames))


def test_two_sources_multiplex_on_one_connection():
    async def run():
        async with StreamServer() as server:
            a = SyntheticMap(n_outer=4, n_inner=8, points_per_second=None, dataset_id="a")
            b = SyntheticRecords(n_samples=50, n_records=3, records_per_second=None, dataset_id="b")
            listening = asyncio.create_task(collect(server.url, n_datasets=2))
            await asyncio.gather(server.feed(a), server.feed(b))
            return await listening

    got = asyncio.run(run())
    assert set(got) == {"a", "b"}
    assert got["b"].frames[-1].arrays["voltage"].shape == (1, 50)


def test_server_rejects_frames_for_unannounced_dataset():
    async def run():
        async with StreamServer() as server:
            src = SyntheticMap(n_outer=2, n_inner=4, points_per_second=None)
            with pytest.raises(ValueError, match="not announced"):
                server.publish_frame(next(src.frames()))

    asyncio.run(run())


def test_feed_surfaces_source_errors():
    class Broken:
        dataset = SyntheticMap(n_outer=2, n_inner=4, points_per_second=None).dataset

        def frames(self):
            raise RuntimeError("producer died")
            yield

    async def run():
        async with StreamServer() as server:
            await server.feed(Broken())

    with pytest.raises(RuntimeError, match="producer died"):
        asyncio.run(run())


def test_paced_replay_follows_recorded_timing(tmp_path):
    src = SyntheticMap(n_outer=10, n_inner=1000, points_per_second=200_000)  # ~50 ms recorded
    path = write_recording(tmp_path / "paced.qdtrec", src)
    t0 = time.perf_counter()
    list(ReplaySource(path, speed=1.0).frames())
    as_recorded = time.perf_counter() - t0
    t0 = time.perf_counter()
    list(ReplaySource(path, speed=None).frames())
    unpaced = time.perf_counter() - t0
    assert as_recorded >= 0.035
    assert unpaced < as_recorded


def test_recording_format_is_rejected_when_corrupt(tmp_path):
    bad = tmp_path / "bad.qdtrec"
    bad.write_bytes(b"not a recording")
    with pytest.raises(ValueError, match="not a qdt recording"):
        list(read_recording(bad))
    good = (FIXTURES / "synthetic_map_64.qdtrec").read_bytes()
    bad.write_bytes(good[:-10])
    with pytest.raises(ValueError, match="truncated"):
        list(read_recording(bad))


def test_sources_satisfy_protocol():
    assert isinstance(SyntheticMap(n_outer=2, n_inner=2), Source)
    assert isinstance(ReplaySource(FIXTURES / "synthetic_map_64.qdtrec"), Source)


def test_wire_path_keeps_design_target_line_rate():
    """A 2048-wide map streamed line-by-line over localhost sustains >= 10^6 pts/s end to end."""
    src = SyntheticMap(n_outer=256, points_per_second=None)  # 524288 points

    async def run():
        async with StreamServer() as server:
            listening = asyncio.create_task(collect(server.url))
            await asyncio.sleep(0.05)  # client connected before the clock starts
            t0 = time.perf_counter()
            await server.feed(src)
            got = await listening
            return got, time.perf_counter() - t0

    got, elapsed = asyncio.run(run())
    n = sum(f.arrays["signal"].size for f in got[src.dataset.dataset_id].frames)
    assert n == 256 * 2048
    assert n / elapsed > 1_000_000
    np.testing.assert_array_equal(
        got[src.dataset.dataset_id].frames[3].arrays["signal"][0], src.row(3)
    )


@pytest.mark.parametrize("name", ["synthetic_map_64", "synthetic_records_8"])
def test_committed_content_oracle_matches_recording(name):
    """The .expected.json oracles (consumed by Flight Deck's decoder tests) agree with the reference
    Python consumer; regenerate both with scripts/make_stream_fixtures.py."""
    import hashlib
    import json

    oracle = json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))
    src = ReplaySource(FIXTURES / f"{name}.qdtrec")
    ds = assemble(src.dataset, src.frames())
    assert oracle["dataset_id"] == src.dataset.dataset_id
    for array_name, spec in oracle["arrays"].items():
        a = ds[array_name].values
        assert list(a.shape) == spec["shape"] and a.dtype.name == spec["dtype"]
        assert (
            hashlib.sha256(a.astype(a.dtype.newbyteorder("<")).tobytes()).hexdigest()
            == spec["sha256"]
        )


def test_feed_publishes_replayed_annotations():
    replay = ReplaySource(FIXTURES / "synthetic_map_64.qdtrec")
    received = live(replay)
    assert [a.annotation_id for a in received.annotations] == ["transition-0"]
