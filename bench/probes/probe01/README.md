# Probe 01 scripts

One-off measurement code for `docs/probes/01-stream-semantics.md`. Not production code; not imported by
anything. Run from a laptop that can reach the instruments.

```
uv run --with qm-qua --with pyvisa --with pyvisa-py python bench/probes/probe01/opx_probe.py --host <opx-ip> --out bench/fixtures/probe01/
uv run --with pyvisa --with pyvisa-py          python bench/probes/probe01/scope_probe.py --resource "TCPIP::<scope-ip>::INSTR" --out bench/fixtures/probe01/
```

Both scripts print a findings summary at the end and write timing CSVs. Copy the summary into the Findings
table of the probe doc. **Check API names against your installed `qm-qua` version first** — the result-handle
and input-stream APIs have shifted across releases; the script isolates each API call so a mismatch fails
one test, not the whole probe.
