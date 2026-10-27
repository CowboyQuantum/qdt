# Analysis 0007 — Phantom as the simulation backend: what qdt and Phantom each need for the cutover

**Date:** 2026-10-27 · **Against:** qdt `main` at `75edffa`; Phantom `main` at `d3a6ce8` (Steps 1–7 built) with
its Step 8 design in `docs/STATUS.md` on `step-8/consumer-contract` (`35caec0`) · **Step:** none yet (the
cutover needs a step file in qdt before any code, ADR 0071)
**Kind:** analysis note. Not a decision. It records what the two repositories hold today, where their
interfaces meet and where they do not, and the work on each side. The human's answers of 2026-10-27 are
recorded at the end; the ADR that opens the cutover in qdt turns them into decisions.
**Issues:** Phantom CowboyQuantum/phantom#40 (Step 8, the consumer contract) and CowboyQuantum/phantom#41
(spin driven by voltages over time, later); qdt #140 (the cutover), #141 (the sequencer interpreter moves
into qdt-lab) and #142 (a scenario names a committed device file).

## 1. The short answer

Phantom was built to replace `qdt-sim`'s physics, and its own documents already describe the cutover:
Phantom's ADR 0003 says qdt consumes Phantom through an adapter that lives in qdt, pins a Phantom release
and contains no physics, and Phantom's Step 8 (`docs/steps/08-qdt-cutover.md`) asks for `qdt-sim` under
300 lines with qdt's CI green against the pinned release. The fit is good:

- The physics inside `qdt-sim`'s `SimulatedDevice` is about twenty lines in one method, `read`. That
  method asks the model for an occupation, a sensor potential and a sensor current, and asks three noise
  processes for a sample at one instant. Phantom's runtime objects answer every one of those calls by
  the same name and with the same arguments.
- Phantom's migrated model reproduces `qdt-sim`'s defaults bit for bit, apart from the corner of the
  stability diagram near zero electrons, where Phantom fixed a double-counting of clipped charge states
  (Phantom's `tests/test_qdt_sim_migration.py`). qdt's fixtures are regenerated once at the cutover in
  any case.
- Both repositories are Apache-2.0, depend only on numpy and scipy for the physics, support the same
  Python versions and promise the same cross-platform agreement, one part in a billion relative.

So the work is interface work, not physics. Measured on this PC with Phantom's gallery device (seed 2,
the gallery's operating point):

| Measurement | Result |
|---|---|
| Compile one device (`compile_device`) | 0.14 s |
| The device as a JSON (JavaScript Object Notation) file | 8 KB |
| The full optimum (`optimum(device)`) | 0.02 s |
| A 64 × 64 noise-free stability map | 0.01 s |

## 2. What each side holds today

**qdt-sim** (1,079 lines of source) has four modules. `dot.py` is the double dot under the
constant-interaction model with a single-electron transistor (SET) as its charge sensor, with three gates:
`P1`, `P2` and `SG`. `noise.py` holds seeded noise processes sampled on a clock. `device.py` is
`SimulatedDevice`, 479 lines, which implements four of qdt-lab's capability protocols for backend
`simulated`: setting levels, sensing levels, running sequencer programs and stepping through loaded lists
on a trigger. `scenarios.py` builds the default device, its stand and the default sweeps, and derives the
truth that tune-up tests compare against. Outside the package, 14 files import it, almost all through
`qdt_sim.scenarios`; only `qdt-server`'s `app.py` imports the model class, to publish its scalar fields
as run options.

**Phantom** has ten layers that import only downward, from `layout` through `electrostatics`, `disorder`,
`valley`, `charge`, `readout`, `spin`, `device` and `optimum`, with `compile` above them all.
`compile_device(layout, CompileParams, seed)` returns a `Device`: a record of parameters, no solver at
run time, serialised as canonical JSON with a format version and the model version of every layer that
produced it. A compiled two-dot device has eight gates (`B_L`, `P1`, `B_M`, `P2`, `B_R`, `SG`, `R_L`,
`R_R`), with its plungers near 0.6 V. `Device.runtime_sensed()` returns a `SensedDoubleDot`, the migrated
`qdt-sim` core. `optimum(device)` returns the best achievable sensor flank, virtual-gate matrix, barrier
voltage for a target tunnel coupling, readout point and exchange sweet spot. Phantom's STATUS holds a
design for its Step 8 that was not started (section 4).

## 3. The seam: what qdt's simulated instrument will call

Most of `SimulatedDevice` is not physics. It maps channels to roles, adds pulse levels to DC levels as a
bias tee does, interprets the body `SimulatedEmitter` writes for a sequencer program, steps loaded lists
on a trigger, records captures, reduces shots and emits stream frames. That is qdt plumbing, and it
moves into qdt-lab (human's answer 1), beside the simulated scope in `qdt_lab.simulated`. What remains
for the physics is a small protocol that the moved interpreter calls and `qdt-sim` implements over
Phantom. In the general layer's words (ADR 0079: no gate, dot or sensor vocabulary in qdt-lab), a sketch:

```python
class SimulatedPhysics(Protocol):
    inputs: tuple[str, ...]
    """Names of the levels the physics responds to, in order; a channel's role is one of them."""
    output: str
    """Name of the role whose channel senses the physics' response."""
    defaults: Mapping[str, float]
    """The level each input holds until a channel sets it (a bias that starts non-zero, for example)."""

    def hold(self, levels: np.ndarray, duration_s: float) -> None:
        """Keep the inputs at `levels` for `duration_s`; time advances, nothing is recorded."""

    def sense(self, levels: np.ndarray, dwell_s: float, samples: int) -> np.ndarray:
        """`samples` readings of the output at `levels`, one every `dwell_s`; time advances."""
```

The clock belongs to the physics, because Phantom's noise and charge dynamics live on it; the
interpreter only says how long each step lasts. qdt-sim's adapter maps `inputs` onto Phantom's gate
names plus one input for the sensor's source–drain bias, and maps `hold` and `sense` onto Phantom's
`Session`. qdt-lab's conformance suite can then test the interpreter with a stub physics, which it cannot
do today because qdt-lab may not import qdt-sim.

## 4. The Phantom side (CowboyQuantum/phantom#40)

Phantom's STATUS already designs the core of its Step 8. It adds `Device.at(v)`, a `State` with the
carried voltages, the occupation, the sensor current, the interdot coupling, the exchange energy and the
compiled rates. It adds `Device.session()`, a `Session` that owns fresh noise processes, a rate equation
for the charge and a clock that only moves forward, with `sense(v_programmed, dwell_s)` returning times,
currents and the charge present, and `wait(duration_s)`. It adds `Device.measure` and `Device.truth`. It
adds one import surface, `phantom.api`, and a contract test, `python -m phantom.contract`, which qdt also
runs. It adds a snapshot of the public interface checked in CI, a changelog, version 0.2.0 and a tag that
the owner creates.

qdt needs six things that the planned interface lacks. Each is cheaper to add before the first tag than
after it:

1. **The sensor's source–drain bias.** The planned `sense` takes gate voltages and a dwell time only.
   qdt's Coulomb-diamond sweep steps the bias as a channel, and the sensor's current scales with it.
   Phantom's `SensedDoubleDot.current_a` already takes the bias, so `Session.sense` needs to pass it on.
2. **A noise seed apart from the device seed.** In Phantom the seed draws the device's disorder: it is
   the device's identity. The plan says a fresh session replays the same noise. qdt gives each run a seed
   to get a new noise realisation on the same device, so `Device.session` needs its own seed, with
   today's behaviour as the default.
3. **Holding voltages for a time without measuring.** The planned `wait` relaxes the charge at the last
   measured point. A qdt pulse step means "go to these voltages and stay there for this long", and the
   charge should evolve at those voltages. Parity with `qdt-sim` does not need it, because `qdt-sim`
   treats pulses as quasi-static; pulsed-gate spectroscopy and spin readout do, and adding it after the
   tag is a breaking change. A `hold(v, duration_s)` or a `wait(duration_s, v)` closes it.
4. **What one sample is.** `qdt-sim` draws a fresh charge state from the Boltzmann distribution for every
   shot, which is how a sensor trace shows switching at a charge degeneracy. Phantom's session can return
   the equilibrium average or a charge trajectory from its rate equation. The contract should say which
   one each sample of `sense` is, and `n_present` should be the sampled state when it is a trajectory.
5. **Truth under the names qdt's tune-up nodes recover.** The `charge-lattice` node recovers the lattice
   in electrons per volt (`l_ij`); Phantom's `charge_lattice` gives it. The `sensor-operating-point` and
   `sensor-wing` nodes recover seven sensor quantities: the peak position nearest a given voltage, the
   period, the charging energy, the lever arm, the width, the wing point and the sensitivity at a given
   bias. Today qdt's `sensor_truth` computes the wing and the sensitivity from the model's parameters,
   which is physics living in qdt. Phantom's `SensorOptimum` returns only the chosen flank voltage and
   its slope. `Device.truth` should carry all seven, so the adapter only renames.
6. **Which fields a user may know.** `Device.operating_point_v` already contains the sensor set point that
   compilation chose: the gallery device's sensor gate is programmed at 0.6 V and compiled onto its flank
   at 0.456 V. A tune-up must start from the programmed point and find the flank itself. Phantom's
   contract should state which fields are knowable (gate names, the programmed point, the layout, the
   temperature) and which are truth, so a consumer that hides truth knows what not to forward.

Later, not part of Step 8 (CowboyQuantum/phantom#41): Phantom's spin readout is shaped as a protocol that
takes a prepared triplet probability, not as the response to voltages over time. qdt's sequencer cannot
drive it until the session carries a spin state that pulses prepare, evolve and read. Dispatch needs the
same thing (ADR 0078 §6).

## 5. The qdt side (#140, #141, #142)

Grouped by issue, in the order they can land.

**#141 — the sequencer interpreter moves into qdt-lab.** `qdt_lab.simulated` gains the interpreter
behind the protocol of section 3, under general names. `qdt-sim` keeps a thin `SimulatedPhysics` over
its own model until the cutover. This is a refactor that changes no output: the committed stability
fixture and every tune-up fixture must reproduce unchanged, which is the proof. It can land before
Phantom tags anything. qdt-lab's conformance suite gains a case for the interpreter with a stub physics.

**#142 — a scenario names a committed device file.** `SimScenario.model` (scalar overrides of
`qdt-sim`'s model) gives way to a reference to a committed Phantom device file: its name and its SHA-256
hash (human's answer 2). The file is 8 KB, diffs line by line, and pins the device even when Phantom's
compile changes; a script with the pinned Phantom compiles the files from their recipes and is the only
writer. `SimScenario.seed` becomes the noise seed only, because the disorder seed is inside the file.
ADR 0048's open problem, that a scenario could not vary a capacitance matrix, goes away: Phantom's
disorder draw varies the matrices. Under qdt's rules this is one commit with the schema, every consumer,
the migration and the tests, and it lands with the cutover, because only Phantom produces device files.

**#140 — the cutover.**
1. **An ADR**: Phantom is an external dependency pinned by git tag (qdt's plan rules out publishing to the
   Python Package Index), imported only by `qdt-sim`. It amends ADR 0078's row for the physics core and
   supersedes the model of ADR 0020. `scripts/check_imports.py` forbids `phantom` in every other package.
2. **The adapter** in `qdt-sim`: loads a device file, opens a session per run, implements
   `SimulatedPhysics`, and exposes the truth functions tests need by the names they use today. Target:
   under 300 lines, as Phantom's Step 8 asks.
3. **The stand from the device**: a DC channel for each of the eight gates, pulse channels on the
   plungers, the bias and the sensor; a gate without a channel holds the programmed point.
4. **Sweeps relative to the device**: `stability()` and `diamonds()` take their default ranges from the
   device's programmed point instead of fixed ranges around 0 V.
5. **Run options**: the server's run options today include "any scalar field of the simulated model",
   published in the OpenAPI document and quoted in Flight Deck's help text (`sensor_width_v`). They
   become the noise seed, whether noise is on, and the device to load. The cold-sensor scenario has no
   direct counterpart, because in Phantom the sensor's width follows from the temperature and the lever
   arm; it becomes a device file compiled colder.
6. **Device lifetime in the server**: a device is loaded once per stand and a fresh session opens per run;
   the levels view (ADR 0057) and the stand state (ADR 0075, 0084) see the same device.
7. **Provenance**: a simulated run's device record carries the Phantom version, the model versions and
   the device file's hash, so every record says which Phantom produced it.
8. **Truth stays out of the API**: read by tests and committed tune-up results only, never by a server
   route (Phantom's ADR 0003).
9. **Regeneration**: the stability fixture, the seven tune-up result fixtures, the schema fixtures and the
   expectations of tutorials 02 to 04; the qdt-analysis injection tests take their truth from Phantom's
   objects. Phantom's own migration fixture then retires.
10. **Phantom's contract test** runs in qdt's CI.

## 6. Order

1. Phantom closes the six gaps of section 4 inside its Step 8 and the owner tags 0.2.0. Nothing in qdt
   changes.
2. qdt moves the interpreter (#141). It needs no Phantom release and no regeneration.
3. qdt writes the cutover's step file and ADR, then lands the adapter, the device files and the
   regenerated fixtures (#140, #142) against the tag.
4. Spin driven by voltages over time (CowboyQuantum/phantom#41), then the qdt sweeps that use it.

## 7. Open questions (settled in review; answers recorded below)

1. Where does the sequencer interpreter live?
2. How does a scenario name its device: a recipe compiled on load, or a committed device file?
3. How often does Phantom release, and how often does qdt move its pin?
4. Does the cutover's timing against deliverables 7 and 8 of Step 6c need a decision? Their tests use the
   simulated stand's channel names, which the cutover changes.

### Answers (human, 2026-10-27)
1. **In qdt-lab**: "move the sequencer interpreter into qdt lab as you say."
2. **A committed device file**: "device file makes more sense."
3. **Held**: "Let's hold off on deciding the release cadence." It stays Phantom Step 8's open decision.
4. **No decision needed**: "I don't see a decision needed for the simulated stand." Deliverables 7 and 8
   proceed on today's simulated stand, and the cutover updates their tests along with every other
   consumer of the stand.
