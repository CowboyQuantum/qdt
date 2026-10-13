"""Record a run: pass its frames through, then write the payload and its `MeasurementRecord` (ADR 0025).

    recorder = RunRecorder(plan, stand, device_id="sim-double-dot")
    source = recorder.wrap(Executor(plan, backends).run())   # stream it, serve it, or just drain it
    for _ in source.frames(): ...
    record, path = recorder.finish(payload_dir)                # then Registry.ingest(record, path)

The recorder holds no database handle (rule 4): it produces the schema objects and a file, and the
registry client stores them. A run that ends before its final frame is recorded as `aborted`, with
unwritten cells NaN (or 0 for integers).
"""

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from qdt_schemas.activity import ExecutionPlan
from qdt_schemas.envelope import MeasurementRecord, PayloadRef
from qdt_schemas.payload_hdf5 import PAYLOAD_TYPE, write_payload
from qdt_schemas.stand import StandConfig

from ..stream.assemble import assemble
from ..stream.frame import Frame
from ..stream.source import Source


class RunRecorder:
    """Collects one run of `plan` on `stand` against `device_id`."""

    def __init__(
        self,
        plan: ExecutionPlan,
        stand: StandConfig,
        device_id: str,
        *,
        campaign: str | None = None,
        record_id: str | None = None,
    ) -> None:
        if plan.stand_id != stand.stand_id:
            raise ValueError(f"plan was compiled for {plan.stand_id!r}, not {stand.stand_id!r}")
        self.plan, self.stand, self.device_id, self.campaign = plan, stand, device_id, campaign
        self.record_id = record_id or uuid.uuid4().hex
        self._frames: list[Frame] = []
        self._started: datetime | None = None

    def wrap(self, source: Source) -> "_Recorded":
        """The same stream, recorded as it passes."""
        if source.dataset != self.plan.dataset:
            raise ValueError("source does not stream this plan's Dataset")
        return _Recorded(self, source)

    def finish(self, payload_dir: str | Path) -> tuple[MeasurementRecord, Path]:
        """Write `<payload_dir>/<YYYY>/<MM>/<record_id>.h5` and return its envelope and path."""
        if self._started is None:
            raise RuntimeError("nothing recorded: iterate the wrapped source first")
        finished = datetime.now(UTC)
        dataset = self.plan.dataset
        xds = assemble(dataset, self._frames)
        arrays = {v.name: xds[v.name].values for v in dataset.data_vars}
        arrays |= {c.name: xds[c.name].values for c in dataset.coords if c.kind == "streamed"}
        relative = f"{self._started:%Y/%m}/{self.record_id}.h5"
        path = Path(payload_dir) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        write_payload(path, dataset, arrays, plan=self.plan, stand=self.stand)
        data = path.read_bytes()
        complete = bool(self._frames) and self._frames[-1].chunk.final
        record = MeasurementRecord(
            record_id=self.record_id,
            device_id=self.device_id,
            stand_id=self.stand.stand_id,
            stand_sha256=self.stand.content_sha256(),
            definition_name=self.plan.definition.name,
            definition_sha256=self.plan.definition.content_sha256(),
            plan_id=self.plan.plan_id,
            source=dataset.source,
            started_at=self._started,
            finished_at=finished,
            outcome="completed" if complete else "aborted",
            campaign=self.campaign,
            payload=PayloadRef(
                type=PAYLOAD_TYPE,
                path=relative,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
            ),
        )
        return record, path


class _Recorded:
    """The `Source` `RunRecorder.wrap` returns."""

    def __init__(self, recorder: RunRecorder, source: Source) -> None:
        self._recorder, self._source = recorder, source
        self.dataset = source.dataset

    def frames(self) -> Iterator[Frame]:
        r = self._recorder
        if r._started is None:
            r._started = datetime.now(UTC)
        for f in self._source.frames():
            r._frames.append(f)
            yield f
