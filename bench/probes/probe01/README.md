# Probe 01: run sheet

Use this sheet for one-off measurements for `docs/probes/01-stream-semantics.md`. None of this is
production code, and nothing imports it. The scripts touch no device, play only zero-amplitude pulses, and
need nothing connected to the instruments.

## Before the lab (any machine, no hardware)
```
uv run --no-project --with qm-qua --with numpy python bench/probes/probe01/opx_probe.py --offline-check
```
Every program must print `ok`. If it fails with the latest `qm-qua`, fix it before the lab day.

## In the lab
Work from the repo root on a laptop on the same network as the OPX1000 and the scope.
`--no-project` keeps `qm-qua`'s pins away from the workspace lock (ADR 0006).

1. **Find the QOP version and gateway.** Use the QM web UI on the cluster, or ask whoever administers
   the OPX. Note the host IP and the cluster name.
2. **Pick `qm-qua` to match.** Start with the latest. If connecting reports an incompatible server,
   install the version QM documents for that QOP release (`--with qm-qua==X.Y.Z`).
3. **Find an LF-FEM slot** (`--fem N`) and an analog output on it (`--ao`, default 1). The probe sets
   that output's DC offset to 0 V and plays only zero-amplitude 16 ns pulses on it. Prefer an output with
   nothing connected.
4. **Offline check with the chosen version:**
   ```
   uv run --no-project --with qm-qua==X.Y.Z --with numpy python bench/probes/probe01/opx_probe.py --offline-check
   ```
5. **Dry run** (~10 s; checks connection, FEM slot and the result APIs):
   ```
   uv run --no-project --with qm-qua==X.Y.Z --with numpy python bench/probes/probe01/opx_probe.py \
       --host <ip> --cluster <name> --fem <slot> --quick --out bench/fixtures/probe01/quick
   ```
   A failing section prints a traceback and the others continue. Usual causes are an API name that
   changed between `qm-qua` versions, or a wrong FEM slot or port.
6. **Full OPX run** (~2 min; ladder 10³–10⁶ points/s plus unpaced, per line and per point, 5 s each):
   ```
   uv run --no-project --with qm-qua==X.Y.Z --with numpy python bench/probes/probe01/opx_probe.py \
       --host <ip> --cluster <name> --fem <slot> --out bench/fixtures/probe01
   ```
7. **Scope run** (~2 min; LAN is simpler than USB with the pure-Python VISA backend):
   ```
   uv run --no-project --with pyvisa --with pyvisa-py python bench/probes/probe01/scope_probe.py \
       --resource "TCPIP::<scope-ip>::INSTR" --out bench/fixtures/probe01
   ```
   "instrument errors: none" at the end means every SCPI command was accepted.
8. **Commit and paste.** Commit `bench/fixtures/probe01/` (CSVs plus `opx_findings.json` and
   `scope_findings.json`). Paste both printed summaries into the Findings table of the probe doc, or leave
   that step for the next session.

The next session writes the contract-freeze ADR from those files. The contract questions each number
answers are under "What the findings decide" in the probe doc.

## What the OPX script measures

| Section | Spec item | Output |
|---|---|---|
| ladder | 1, 2: granularity, sustained rate | delivered points/s, inter-arrival median/p95, fetch µs per point, data loss, per run |
| granularity | 1: partial buffers | is anything visible or fetchable from a whole-frame buffer before it completes? |
| addressing | 3, 4 | positional check (value == loop index), dtype and shape on fetch |
| runtime | 5: no recompile | one compiled program run twice with different step count, step size (so endpoint) and averaging count via input streams; IO1 via pause/resume |
| timestamps | 3: timestamp cost | delivered rate with a timestamp stream attached; OPX-clock spacing |
