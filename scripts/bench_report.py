"""pytest plugin: write `bench/reports/<YYYY-MM-DD>-step<N>.md` after any run of `hardware` tests.

Loaded through `-p bench_report` in `addopts` (`pythonpath = ["scripts"]`). It watches every test that
carries the `hardware` marker; when at least one of them actually executed (reached its call phase, so
not only skipped for a missing address) the session appends one "Run" section to the day's report, and
creates the file with its header if the day has none. CI never writes a report: it deselects `hardware`.

A report files itself under the step that planned its tests (#77): the test module's `PLANNED_BY`
(ADR 0071) names a step file, `docs/steps/<NN>-…`, or ADRs whose `**Step:**` line is a step number;
the first step file, else the highest-numbered ADR that resolves, is the step. A run that executes tests of several steps writes a section to
each step's report. A test that resolves to no step files under the `bench_step` ini value, or
`unplanned` when that is empty too.

Rule 7: addresses and credentials never reach the file. The values of every `QDT_*_ADDRESS` and
`QDT_*_DSN` variable, anything that looks like an IPv4 address, a VISA resource string or a URL with
credentials, and the stand file name are replaced before any text is written.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

MARKER = "hardware"
_SECRET_VAR = re.compile(r"^QDT_\w*_(?:ADDRESS|DSN)$")
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_VISA = re.compile(r"\b(?:TCPIP|GPIB|USB|ASRL)\d*::[^\s'\"`]*", re.IGNORECASE)
_CREDENTIALED_URL = re.compile(r"\b[a-z][\w+.-]*://[^\s'\"`/@]*@[^\s'\"`]*", re.IGNORECASE)
_STAND_FILE = re.compile(r"[\w./-]*\.stand\.json\b")
_PARAM_ID = re.compile(r"\[([^\]]*)\]$")
_STEP_FILE = re.compile(r"^docs/steps/0*(\d+[a-z]?)-")
_ADR_REF = re.compile(r"^ADR (\d{4})$")
_ADR_STEP = re.compile(r"^\*\*Step:\*\*\s*0*(\d+[a-z]?)\b", re.MULTILINE)


@dataclass
class Outcome:
    """One hardware test's result across its three phases."""

    nodeid: str
    setup: str | None = None
    call: str | None = None
    duration: float = 0.0
    message: str | None = None
    step: str | None = None
    """The step that planned the test (`step_of`); None files under the fallback."""

    @property
    def outcome(self) -> str:
        if self.setup == "skipped":
            return "skipped"
        if self.setup == "failed":
            return "error"
        return self.call or "error"

    @property
    def executed(self) -> bool:
        """Reached its call phase and did not skip there: it proved or disproved something."""
        return self.call is not None and self.call != "skipped"

    @property
    def backend(self) -> str:
        """The parametrize id: the backend in the conformance suite, the case in a bench test."""
        m = _PARAM_ID.search(self.nodeid)
        return m.group(1) if m else "—"

    @property
    def test(self) -> str:
        nodeid = _PARAM_ID.sub("", self.nodeid)
        path, _, name = nodeid.rpartition("::")
        return f"{Path(path).name}::{name}" if path else name


@dataclass
class _Collector:
    step: str
    outcomes: dict[str, Outcome] = field(default_factory=dict)


def step_of(planned_by, root: Path) -> str | None:
    """The step a test's `PLANNED_BY` resolves to: the number of the first step file it names
    (`docs/steps/06c-…` → `6c`), else the `**Step:**` of the highest-numbered ADR it names whose line
    is a step number (the newest ADR is the one that planned the newest row); None when neither
    resolves."""
    refs = (planned_by,) if isinstance(planned_by, str) else tuple(planned_by or ())
    for ref in refs:
        if m := _STEP_FILE.match(str(ref)):
            return m.group(1)
    adrs = sorted((m.group(1) for ref in refs if (m := _ADR_REF.match(str(ref)))), reverse=True)
    for number in adrs:
        for adr in sorted((root / "docs" / "adr").glob(f"{number}-*.md")):
            try:
                text = adr.read_text(encoding="utf-8")
            except OSError:
                continue
            if found := _ADR_STEP.search(text):
                return found.group(1)
    return None


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        "bench_step",
        "Step number for bench report file names when a test's PLANNED_BY resolves to none",
        default="",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.pluginmanager.register(_Plugin(config.getini("bench_step")), "bench_report_collector")


class _Plugin:
    def __init__(self, step: str) -> None:
        self._c = _Collector(step=step)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo):
        result = yield
        report: pytest.TestReport = result.get_result()
        if item.get_closest_marker(MARKER) is None:
            return
        o = self._c.outcomes.setdefault(item.nodeid, Outcome(item.nodeid))
        if o.step is None:
            planned = getattr(getattr(item, "module", None), "PLANNED_BY", None)
            o.step = step_of(planned, item.config.rootpath)
        o.duration += report.duration
        if report.when == "setup":
            o.setup = report.outcome
        elif report.when == "call":
            o.call = report.outcome
        if report.outcome in ("failed", "skipped") and o.message is None:
            o.message = _first_line(report)

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        root = session.config.rootpath
        now = datetime.now(UTC)
        args = " ".join(str(a) for a in session.config.invocation_params.args)
        commit = _commit(root)
        fallback = self._c.step or "unplanned"
        by_step: dict[str, list[Outcome]] = {}
        for o in self._c.outcomes.values():
            by_step.setdefault(o.step or fallback, []).append(o)
        for step, outcomes in sorted(by_step.items()):
            if not any(o.executed for o in outcomes):
                continue
            path = root / "bench" / "reports" / f"{now:%Y-%m-%d}-step{step}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            section = render_run(outcomes, now=now, commit=commit, command=args)
            if path.exists():
                path.write_text(
                    path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + section, "utf-8"
                )
            else:
                path.write_text(render_header(now, step) + "\n" + section, encoding="utf-8")
            session.config.stash.setdefault(REPORT_PATH, path)


REPORT_PATH = pytest.StashKey[Path]()


def _first_line(report: pytest.TestReport) -> str:
    crash = getattr(report.longrepr, "reprcrash", None)
    if crash is not None:
        text = str(crash.message)
    elif isinstance(report.longrepr, tuple):
        text = str(report.longrepr[2])
    else:
        text = str(report.longrepr)
    return text.strip().splitlines()[0] if text.strip() else ""


def _commit(root: Path) -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown commit"
    return f"commit {sha}" + (" (dirty)" if dirty else "")


def redact(text: str) -> str:
    """Replace every instrument or server address and every DSN with `<address>` (rule 7)."""
    for name, value in os.environ.items():
        if _SECRET_VAR.match(name) and value:
            text = text.replace(value, "<address>")
    text = _CREDENTIALED_URL.sub("<address>", text)
    text = _VISA.sub("<address>", text)
    text = _IPV4.sub("<address>", text)
    return _STAND_FILE.sub("<stand file>", text)


def render_header(now: datetime, step: str) -> str:
    return (
        f"# Bench report — {now:%Y-%m-%d} (Step {step})\n\n"
        "Hardware-marked tests run from the bench, one section per run, newest last. Written by\n"
        "`scripts/bench_report.py`; do not edit by hand. Instrument addresses are not recorded (rule 7).\n"
    )


def render_run(outcomes: list[Outcome], *, now: datetime, commit: str, command: str) -> str:
    counts = {
        k: sum(o.outcome == k for o in outcomes) for k in ("passed", "failed", "skipped", "error")
    }
    total = sum(o.duration for o in outcomes)
    lines = [
        f"## Run {now:%H:%M} UTC — {commit}",
        "",
        f"Command: `pytest {redact(command)}`  ",
        (
            f"Result: {counts['passed']} passed, {counts['failed']} failed, "
            f"{counts['skipped']} skipped, {counts['error']} errors in {total:.1f} s"
        ),
        "",
        "| Case | Passed | Failed | Skipped | Errors |",
        "|---|---|---|---|---|",
    ]
    for backend in sorted({o.backend for o in outcomes}):
        group = [o for o in outcomes if o.backend == backend]
        row = [sum(o.outcome == k for o in group) for k in ("passed", "failed", "skipped", "error")]
        lines.append(f"| {backend} | " + " | ".join(str(n) for n in row) + " |")
    lines += ["", "| Test | Case | Outcome | Time |", "|---|---|---|---|"]
    for o in outcomes:
        lines.append(f"| {o.test} | {o.backend} | {o.outcome} | {o.duration:.2f} s |")
    notes = [o for o in outcomes if o.message and o.outcome != "passed"]
    if notes:
        lines += ["", "Messages:", ""]
        for o in notes:
            lines.append(f"- `{o.test}[{o.backend}]` {o.outcome}: {redact(o.message or '')}")
    return "\n".join(lines) + "\n"
