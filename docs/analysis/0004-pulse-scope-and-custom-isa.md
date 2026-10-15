# Analysis 0004 — Revisiting plan §10: frames, envelopes, branching, feedback; and custom-ISA processors

**Date:** 2026-10-15 · **Informs:** future ADRs amending §10; backend capability declarations · **Step:** 6+
**Kind:** analysis note. Not a decision. Parked for revisit; nothing here is scheduled.

## 1. What §10 excludes, and what each would cost

Contracts at stake: positional results and exact declared coordinates (ADR 0015, 0017), the executor never
understanding a backend language (`check_run`), the simulated backend as the first ISA (ADR 0018), the
raw `SequencerProgram` escape hatch on a stage.

| Capability | What it is | Why a spin-qubit lab wants it | Breaks contracts? | Middle path |
|---|---|---|---|---|
| Phase-tracked frames | Per-channel rotating-frame phase accumulated across pulses; virtual Z = frame advance | Any coherent experiment past Rabi (Ramsey, echo, 2q gates, RB) | No | `shift_frame(ch, phi)`, `reset_frame(ch)`; `drive` phase relative to frame |
| Named envelopes + channel filters | `gaussian`, `flattop`, `drag` as parametric primitives; predistortion as a `ChannelMap` filter | Shaped pulses; bias-tee/line correction | No | Envelopes in the sequence; filters on the stand, never in the sequence |
| Balanced branching | `conditional(segment, on=measure > threshold)` with equal-duration, equal-result branches; branch taken emitted as a result stream | Active reset; conditional readout | No, if balanced | Admit when initialization time dominates |
| Full waveform algebra | Sample-level construction: sums, products, windows, arbitrary arrays | Rare once envelopes + filters exist | Partly (unbounded content, memory limits, custom ISAs can't) | Keep out; escape hatch |
| In-sequencer feedback | Sub-µs loop mutating parameters from outcomes | Drift tracking, adaptive estimation | Yes (plan no longer describes what played) | Keep out; executor-level loop (Step 6) exists. If ever admitted: applied parameters must be emitted as data |

Governance: each admission is an ADR amending §10 and lands as a **quartet** — the primitive, its semantics
in the simulated interpreter, emitter support in ≥1 real backend, and its `check_run` rules — never a
primitive without its simulated meaning. Once primitives exist that not every backend executes, a
**backend capability declaration** on `InstrumentConfig` (tick, parameter width, program length, channel
count, supported primitives) becomes required so an emitter refuses at compile time rather than degrading.

## 2. Where they live

Cost is in four places regardless of repo: schema primitive, simulated interpreter, emitter, `check_run`.
Off-repo adds a fifth (a plugin contract across a version boundary) and is not worth building at one
contributor. The sorting:
- **Core `qdt_schemas.pulse`:** frames, named envelopes.
- **Separate workspace package, same repo (lockstep version, optional extra):** balanced branching and
  anything needing a discrete-outcome measurement model in `qdt-sim`.
- **Off-repo via the escape hatch:** waveform algebra, in-sequencer feedback, as a research sequencer
  emitting raw `SequencerProgram`s; promoted inward by ADR if proven.

## 3. Custom-ISA processors (DC or AWG)

- A custom DC controller is a `LevelSource` (+`LevelSense`); its ISA is a transport detail.
- A self-clocked custom AWG is a `Sequencer`; hybrids implement both. Extension = emitter (pure, golden-tested)
  → emulator (ADR 0041 pattern) → transport → driver → `FACTORIES` → ladder. Nothing above the drivers changes.
- Known friction: clock granularity unknown to `check_run` (capability declaration fixes it); processors that
  source but do not sense need the deferred per-point `WaveformSense` path (ADR 0019/0021); ISA features
  beyond the primitives go through the escape hatch.
- A processor the project *builds* (HDL, test bench, firmware, bitstreams) is its own repo by the org test
  (toolchain, cadence, audience); it owns the ISA and publishes it as a small versioned package the qdt
  emitter pins. `SequencerProgram` with `backend="<isa>"` is the inter-repo contract. A board someone else
  built is just a driver and an emitter in qdt.
- If designing an ISA from scratch: make integer parameter registers with scale, an innermost shot counter, a
  positional result FIFO, and align/sticky-level semantics native, so the emitter is near-identity.
