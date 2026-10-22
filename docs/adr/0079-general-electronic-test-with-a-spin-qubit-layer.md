# 0079 — qdt is a general electronic test toolkit with a spin-qubit layer on top; the general layer knows no domain words, and a second-domain suite keeps it honest

**Status:** Proposed
**Date:** 2026-10-22
**Step:** process; the first items are issues under label `generality`

## Context
Measurement software built around one job tends to harden into that job: a toolkit tuned to spin-qubit
calibration that cannot run an S-parameter sweep, an FFT of a captured signal, an IV curve, or an IC
verification task without a rewrite. The human has seen this elsewhere and asked whether qdt is starting
down that road (2026-10-22). The architecture is domain-neutral — capability protocols, sweeps as axes over
channels with a declared quantity, a coordinate-addressed Dataset, an envelope that carries any payload,
analysis as pure functions — and an IV curve on the SMU already works unchanged. But the vocabulary has
narrowed in three places that frozen slices will otherwise cement:
- `Quantity = Literal["voltage", "current"]` (stand.py): no frequency, power, phase, resistance,
  temperature, time or dimensionless, so a VNA or a thermal test cannot even be declared.
- `DType` is real-valued only: S-parameters, IQ data and FFT output are complex.
- No protocol for an instrument that sweeps internally and returns a trace against an axis it supplies
  (VNA, spectrum analyser); `WaveformSense` is the time-axis special case only.
Smaller signs: all five curated analysis methods are dot methods and none is an FFT; a few domain words sit
in the general packages (4 at baseline: "virtual gate" in activity/compile/execute, "cooldown" in the
envelope).

## Decision
1. **Stance.** qdt is a general electronic test toolkit. The **spin-qubit layer** — `qdt-tuning`, the dot
   methods in `qdt-analysis`, the Virtual gates widget, `qdt-sim`/`phantom` — sits on top of it. The
   **general layer** — `qdt-schemas`, `qdt-lab`, `qdt-registry`, `qdt-server`'s mechanisms, Flight Deck as
   a workspace — must not know what a gate, a dot or a qubit is.
2. **Vocabulary check.** `scripts/check_vocabulary.py` greps the general packages for the terms in
   `scripts/vocabulary_terms.txt` and fails CI on any hit beyond the committed baseline; the baseline may
   only shrink. `qdt-server`'s tune-up routes are the spin layer's API surface and are exempt.
3. **Widen the vocabulary now, additively.** `Quantity` gains `frequency`, `power`, `phase`, `resistance`,
   `temperature`, `time`, `dimensionless`, each with its SI unit (dBm is a display unit of power); `DType`
   gains `complex64` and `complex128`. Arrow has no complex type, so complex arrays travel as interleaved
   float pairs (a trailing axis of length 2) declared complex in the schema and decoded on both ends.
   Adding literal values breaks no existing payload: a minor `schema_version` bump, no migration — but only
   while few slices depend on them, which is now.
4. **One more protocol, generic.** `TraceSense`: a capture whose axis the instrument supplies, of any
   quantity. `WaveformSense` becomes its time-axis case. VNA, spectrum analyser and scope all implement it.
   Digital I/O for IC verification is a later protocol with its own ADR.
5. **A standing second-domain suite** in L0 against emulators, so the general layer is exercised by
   something other than tuning on every commit: an IV curve on the SMU (works now); an FFT of a captured
   waveform (one generic method, captures recorded); an S-parameter sweep on an emulated VNA (needs 3–4).
   The human's home bench gives the first two an L2 row with real instruments.
6. **Labels from data.** Anything Flight Deck shows as a category — channel types, stages — comes from the
   stand configuration, so a bench stand reads "supply, DUT, probe" and a dot stand "plunger, barrier,
   sensor" with no code change.

## Consequences
- Easier: a VNA, a thermal test or an IC verification task is a stand file and a driver, not a redesign;
  the spin-qubit layer stays exactly as capable; a newcomer from electronics test finds familiar words.
- Harder: three slices take a minor version bump; the Dataset decoder on both ends learns complex; four
  baseline hits must be renamed when touched (`virtual gate` → a neutral name for a linear channel
  transform; `cooldown` → a neutral run-context name) with migrations.
- Must now: file the `generality` issues (`scripts/issues_generality.py`); do the `Quantity`/`DType`
  widening first, since it has a deadline; keep the vocabulary ratchet green.

## Alternatives considered
- Leave the vocabulary closed and add a second toolkit for electronics later — rejected: that is the
  failure the human described, with the rewrite deferred rather than avoided.
- Make `Quantity` a free string — rejected: validation and unit handling are worth a closed, wide enum.
- Remove the spin-qubit layer from qdt to force generality — rejected: the layer is the product's first
  purpose; the point is that it sits on top, not that it goes away.
