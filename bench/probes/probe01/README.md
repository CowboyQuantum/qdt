# Probe 01 scripts

One-off measurement scripts for `docs/probes/01-stream-semantics.md`. None of this is
production code, and nothing imports it. The scripts touch no device, play only zero-amplitude pulses, and
need nothing connected to the instruments.

**To run the probe, follow [LAB_GUIDE.md](LAB_GUIDE.md).** It has the steps, the commands, what a good run
looks like, and what to do if something fails.

Quick check you can run on any machine before the lab day:
```
uv run --no-project --with qm-qua --with numpy python bench/probes/probe01/opx_probe.py --offline-check
```

## What the OPX script measures

| Section | Spec item | Output |
|---|---|---|
| ladder | 1, 2: granularity, sustained rate | delivered points/s, inter-arrival median/p95, fetch µs per point, data loss, per run |
| granularity | 1: partial buffers | is anything visible or fetchable from a whole-frame buffer before it completes? |
| addressing | 3, 4 | positional check (value == loop index), dtype and shape on fetch |
| runtime | 5: no recompile | one compiled program run twice with different step count, step size (so endpoint) and averaging count via input streams; IO1 via pause/resume |
| timestamps | 3: timestamp cost | delivered rate with a timestamp stream attached; OPX-clock spacing |
