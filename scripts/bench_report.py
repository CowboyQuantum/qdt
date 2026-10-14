"""pytest plugin: write `bench/reports/<YYYY-MM-DD>-step<N>.md` after any run of `hardware` tests.

Loaded through `-p bench_report` in `addopts` (`pythonpath = ["scripts"]`). It watches every test that
carries the `hardware` marker; when at least one of them actually executed (reached its call phase, so
not only skipped for a missing address) the session appends one "Run" section to the day's report, and
creates the file with its header if the day has none. CI never writes a report: it deselects `hardware`.

Rule 7: addresses never reach the file. The values of every `QDT_*_ADDRESS` variable, anything that
looks like an IPv4 address or a VISA resource string, and the stand file name are replaced before any
text is written.
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
_ADDRESS_VAR = re.compile(r"^QDT_\w*_ADDRESS$")
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_VISA = re.compile(r"\b(?:TCPIP|GPIB|USB|ASRL)\d*::[^\s'\"`]*", re.IGNORECASE)
_STAND_FILE = re.compile(r"[\w./-]*\.stand\.json\b")
_PARAM_ID = re.compile(r"\[([^\]]*)\]$")


@dataclass
class Outcome:
    """One hardware test's result across its three phases."""

    nodeid: str
    setup: str | None = None
    call: str | None = None
    duration: float = 0.0
    message: str | None = None

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


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini("bench_step", "Step number named in bench report file names", default="")


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
        o.duration += report.duration
        if report.when == "setup":
            o.setup = report.outcome
        elif report.when == "call":
            o.call = report.outcome
        if report.outcome in ("failed", "skipped") and o.message is None:
            o.message = _first_line(report)

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        outcomes = list(self._c.outcomes.values())
        if not any(o.executed for o in outcomes):
            return
        root = session.config.rootpath
        now = datetime.now(UTC)
        path = root / "bench" / "reports" / f"{now:%Y-%m-%d}-step{self._c.step}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        args = " ".join(str(a) for a in session.config.invocation_params.args)
        section = render_run(outcomes, now=now, commit=_commit(root), command=args)
        if path.exists():
            path.write_text(
                path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + section, "utf-8"
            )
        else:
            path.write_text(render_header(now, self._c.step) + "\n" + section, encoding="utf-8")
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
    """Replace every instrument address with `<address>` (rule 7)."""
    for name, value in os.environ.items():
        if _ADDRESS_VAR.match(name) and value:
            text = text.replace(value, "<address>")
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
