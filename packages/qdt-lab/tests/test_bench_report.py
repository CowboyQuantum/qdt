"""`scripts/bench_report.py`: a run of `hardware` tests leaves a dated, address-free report."""

import re
from datetime import UTC, datetime

import pytest
from bench_report import Outcome, redact, render_run, step_of

pytest_plugins = "pytester"

INI = """
[tool.pytest.ini_options]
markers = ["hardware: requires bench instruments"]
bench_step = "5"
"""

TESTS = """
import os, pytest

@pytest.mark.hardware
@pytest.mark.parametrize("backend", ["opx1000", "qdac2"])
def test_level(backend):
    if backend == "qdac2":
        pytest.skip("QDT_QDAC2_ADDRESS not set")
    assert True

@pytest.mark.hardware
def test_boom():
    raise ConnectionError("TCPIP::10.20.30.40::5025::SOCKET refused")

def test_plain():
    assert True
"""


def _report(pytester: pytest.Pytester, step: str = "5"):
    return pytester.path / "bench" / "reports" / f"{datetime.now(UTC):%Y-%m-%d}-step{step}.md"


def test_a_hardware_run_writes_the_days_report(pytester: pytest.Pytester):
    pytester.makepyprojecttoml(INI)
    pytester.makepyfile(TESTS)
    result = pytester.runpytest("-p", "bench_report", "-m", "hardware")
    result.assert_outcomes(passed=1, skipped=1, failed=1)
    text = _report(pytester).read_text(encoding="utf-8")
    assert text.startswith("# Bench report — ") and "(Step 5)" in text
    assert text.count("## Run ") == 1
    assert "Result: 1 passed, 1 failed, 1 skipped, 0 errors" in text
    assert "| opx1000 | 1 | 0 | 0 | 0 |" in text
    assert "| qdac2 | 0 | 0 | 1 | 0 |" in text
    assert (
        "| test_a_hardware_run_writes_the_days_report.py::test_level | opx1000 | passed |" in text
    )
    assert (
        "`test_a_hardware_run_writes_the_days_report.py::test_boom[—]` failed: ConnectionError"
        in text
    )
    assert "10.20.30.40" not in text and "TCPIP::" not in text


def test_a_second_run_the_same_day_appends_a_section(pytester: pytest.Pytester):
    pytester.makepyprojecttoml(INI)
    pytester.makepyfile(TESTS)
    pytester.runpytest("-p", "bench_report", "-m", "hardware", "-k", "opx1000")
    pytester.runpytest("-p", "bench_report", "-m", "hardware", "-k", "opx1000")
    text = _report(pytester).read_text(encoding="utf-8")
    assert text.count("# Bench report") == 1
    assert text.count("## Run ") == 2


def test_no_report_when_no_hardware_test_executed(pytester: pytest.Pytester):
    pytester.makepyprojecttoml(INI)
    pytester.makepyfile(TESTS)
    pytester.runpytest("-p", "bench_report", "-m", "not hardware").assert_outcomes(passed=1)
    assert not _report(pytester).exists()
    pytester.runpytest("-p", "bench_report", "-m", "hardware", "-k", "qdac2").assert_outcomes(
        skipped=1
    )
    assert not _report(pytester).exists(), "a run that only skipped proves nothing"


def test_redact_hides_every_address_form(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDT_OPX_ADDRESS", "opx-gateway.lab")
    text = (
        "host opx-gateway.lab, 192.168.1.20, TCPIP::scope.lab::INSTR, GPIB0::24::INSTR, "
        "stand bench.stand.json"
    )
    out = redact(text)
    assert "opx-gateway.lab" not in out and "192.168" not in out and "scope.lab" not in out
    assert "GPIB0" not in out and "bench.stand.json" not in out
    assert out.count("<address>") == 4 and "<stand file>" in out


def test_render_run_counts_and_classifies_outcomes():
    outcomes = [
        Outcome("tests/test_x.py::test_a[qdac2]", setup="passed", call="passed", duration=0.5),
        Outcome("tests/test_x.py::test_b[qdac2]", setup="failed", message="boom"),
        Outcome("tests/test_x.py::test_c[k2400]", setup="skipped", message="unset"),
    ]
    text = render_run(
        outcomes, now=datetime(2026, 10, 14, 12, 0, tzinfo=UTC), commit="commit abc", command="x"
    )
    assert text.startswith("## Run 12:00 UTC — commit abc")
    assert "Result: 1 passed, 0 failed, 1 skipped, 1 errors in 0.5 s" in text
    assert re.search(r"\| qdac2 \| 1 \| 0 \| 0 \| 1 \|", text)
    assert "| test_x.py::test_b | qdac2 | error |" in text
    assert "- `test_x.py::test_c[k2400]` skipped: unset" in text


# --- a report files itself under the step that planned its tests (#77) ---------------------------

ADR = """# 0099 — Something the bench proves

**Status:** Accepted
**Date:** 2026-10-01
**Step:** 6 open decision (closes nothing)
"""


def test_step_of_resolves_a_step_file_then_an_adr(tmp_path):
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / "0099-something.md").write_text(ADR, encoding="utf-8")
    assert step_of(("docs/steps/06c-lab-deployment.md",), tmp_path) == "6c"
    assert step_of(("ADR 0099", "docs/steps/05-drivers.md"), tmp_path) == "5"
    assert step_of(("ADR 0040", "ADR 0099"), tmp_path) == "6"  # 0040 is not under this root
    assert step_of("ADR 0099", tmp_path) == "6"
    assert step_of(("ADR 0001",), tmp_path) is None
    assert step_of(None, tmp_path) is None


def test_runs_file_under_the_step_that_planned_them(pytester: pytest.Pytester):
    pytester.makepyprojecttoml(INI)
    pytester.mkdir("docs").joinpath("adr").mkdir()
    pytester.path.joinpath("docs", "adr", "0099-something.md").write_text(ADR, encoding="utf-8")
    pytester.makepyfile(
        test_step_file="""
import pytest
PLANNED_BY = ("docs/steps/06c-lab-deployment.md",)

@pytest.mark.hardware
def test_remote():
    assert True
""",
        test_adr="""
import pytest
PLANNED_BY = ("ADR 0099",)

@pytest.mark.hardware
def test_segments():
    assert True
""",
        test_unplanned="""
import pytest

@pytest.mark.hardware
def test_legacy():
    assert True
""",
    )
    result = pytester.runpytest("-p", "bench_report", "-m", "hardware")
    result.assert_outcomes(passed=3)
    by_step_file = _report(pytester, "6c").read_text(encoding="utf-8")
    assert "(Step 6c)" in by_step_file and "test_step_file.py::test_remote" in by_step_file
    assert "test_segments" not in by_step_file and "test_legacy" not in by_step_file
    assert "Result: 1 passed, 0 failed, 0 skipped, 0 errors" in by_step_file
    by_adr = _report(pytester, "6").read_text(encoding="utf-8")
    assert "(Step 6)" in by_adr and "test_adr.py::test_segments" in by_adr
    fallback = _report(pytester, "5").read_text(encoding="utf-8")  # the ini value
    assert "test_unplanned.py::test_legacy" in fallback


def test_without_an_ini_step_an_unplanned_test_files_as_unplanned(pytester: pytest.Pytester):
    pytester.makepyprojecttoml(INI.replace('bench_step = "5"\n', ""))
    pytester.makepyfile(TESTS)
    pytester.runpytest("-p", "bench_report", "-m", "hardware", "-k", "opx1000")
    assert _report(pytester, "unplanned").exists()


def test_redact_hides_dsns_and_server_addresses(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDT_READER_DSN", "postgresql+psycopg://qdt_reader:s3cret@db-host:5432/qdt")
    monkeypatch.setenv("QDT_READ_SERVER_ADDRESS", "http://db-host:8700")
    text = (
        "dsn postgresql+psycopg://qdt_reader:s3cret@db-host:5432/qdt, server http://db-host:8700, "
        "another sqlite:///file:x.sqlite?mode=ro, with creds mysql://u:p@h/db"
    )
    out = redact(text)
    assert "s3cret" not in out and "db-host" not in out and "u:p@h" not in out
    assert "sqlite:///file:x.sqlite?mode=ro" in out  # no credentials, no host: nothing to hide
