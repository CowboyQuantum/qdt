"""Analysis output payloads (ADR 0031): stored once beside the result, read back as a Dataset, synced
after the result's record, and refused when they do not match."""

import numpy as np
import pytest

from qdt_analysis.transitions import detect_transitions
from qdt_registry import Registry
from qdt_schemas.data import SourceDescriptor


def analysed(reg: Registry, record):
    return detect_transitions(record, reg.payload(record.record_id))


def test_output_is_written_once_read_back_and_synced(tmp_path, server, device, recorded_run):
    dsn, store = server
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=store)
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path, n=(32, 32))
    reg.ingest(record, path)
    result, output = analysed(reg, record)
    assert result.output is None and output is not None

    stored = reg.add_result(result, output)
    assert stored.output is not None
    assert stored.output.path == f"analysis/{stored.created_at:%Y/%m}/{stored.result_id}.h5"
    assert (reg.store / stored.output.path).stat().st_size == stored.output.size_bytes
    back = reg.output(stored.result_id)
    assert back.dataset == output.dataset
    assert back.dataset.source.kind == "analysis"
    np.testing.assert_array_equal(back.arrays["gradient"], output.arrays["gradient"])
    np.testing.assert_array_equal(back.arrays["edges"], output.arrays["edges"])
    assert back.annotations == output.annotations

    assert reg.add_result(stored) == stored  # idempotent: the file is already there
    assert reg.add_result(result, output) == stored  # or re-adding with the same arrays

    report = reg.sync()
    assert report.analysis_results == 1
    assert report.payload_bytes == record.payload.size_bytes + stored.output.size_bytes
    assert (store / stored.output.path).read_bytes() == (reg.store / stored.output.path).read_bytes()
    assert reg.results(record_id=record.record_id, remote=True) == [stored]
    assert reg.result(stored.result_id, remote=True) == stored
    assert reg.sync().payload_bytes == 0


def test_result_without_output_has_none(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path, n=(32, 32))
    reg.ingest(record, path)
    result, _ = analysed(reg, record)
    stored = reg.add_result(result)
    assert stored == result and stored.output is None
    with pytest.raises(KeyError, match="no output"):
        reg.output(stored.result_id)
    with pytest.raises(KeyError, match="no analysis result"):
        reg.result("0" * 32)


def test_output_must_be_an_analysis_dataset_and_match_its_reference(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path, n=(32, 32))
    reg.ingest(record, path)
    result, output = analysed(reg, record)
    wrong_kind = output._replace(
        dataset=output.dataset.model_copy(update={"source": SourceDescriptor(kind="synthetic")})
    )
    with pytest.raises(ValueError, match="source.kind 'analysis'"):
        reg.add_result(result, wrong_kind)
    stored = reg.add_result(result, output)
    with pytest.raises(ValueError, match="one or the other"):
        reg.add_result(stored, output)
    missing = stored.model_copy(
        update={"output": stored.output.model_copy(update={"sha256": "1" * 64})}
    )
    with pytest.raises(ValueError, match="not in this client's store"):
        reg.add_result(missing)
