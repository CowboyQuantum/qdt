# Step 6d — The Phantom cutover

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.
> Inserted beside Step 6c by ADR 0087 (human, 2026-10-28: "Phantom cutover now"). Design: Analysis 0007
> (`docs/analysis/0007-phantom-as-the-simulation-backend.md`), with the human's answers of 2026-10-27.
> Issues: #141 (the interpreter into qdt-lab), #140 (the cutover), #142 (a scenario names a device file);
> Phantom's side is CowboyQuantum/phantom#40, released as `v0.2.0` (tag at `f72daac`).

## Goal
`qdt-sim` becomes an adapter over a pinned Phantom release and contains no physics. The sequencer
interpreter that today sits inside `qdt-sim`'s `SimulatedDevice` moves into `qdt_lab.simulated` behind a
small physics protocol, so the simulator's physics can be swapped without touching the instrument layer.
qdt's committed simulator outputs are regenerated once, against Phantom, and every consumer follows.

## Schema slice
`SimScenario` (`qdt_schemas.modeling`, ADR 0048) names a committed Phantom device file by its name and
SHA-256 instead of carrying overrides of `qdt-sim`'s model, and its `seed` becomes the noise seed only
(#142). A `schema_version` bump (to 2) in one commit with every consumer; no migration, since neither
`SimScenario` nor `SimResult` is persisted (ADR 0088).
`qdt-schemas` still knows nothing about Phantom (rule 1): the reference is a file name and a hash.

## Deliverables
**First, without Phantom (#141)**
1. `qdt_lab.simulated` gains the sequencer interpreter as a generic simulated instrument implementing
   `LevelSource`, `LevelSense`, `Sequencer` and `TriggeredLevelSource` for backend `simulated`, over a
   `SimulatedPhysics` protocol (inputs, an output, default levels, a clock it owns, `hold` and `sense`).
   General words only (ADR 0079; `scripts/check_vocabulary.py`).
2. `qdt-sim` keeps `SimulatedDevice` as that instrument over a thin physics on its own model and noise,
   with the same constructor and attributes, until the cutover. Every output stays bit-identical: the
   committed stability fixture and the seven `SimResult` fixtures reproduce without regeneration, and
   every existing test passes unchanged.
3. qdt-lab's conformance suites for the level source and the triggered level source gain the interpreter
   on a stub physics (`LinearPhysics`), and a test runs emitted sequences on it: impossible before,
   because qdt-lab may not import qdt-sim. The level-sense suite does not fit it (it senses the channel it
   sets, and times the wall clock), nor does the sequencer suite (its program is the flat-index one).

**Then, against `v0.2.0` (#140 and #142, one pull request)**
4. Phantom as a dependency of `qdt-sim` only, pinned by git tag (`uv.lock` carries the commit);
   `scripts/check_imports.py` forbids `phantom` in every other package and any import but `phantom.api`.
5. The adapter in `qdt-sim`: loads a committed device file, opens a Phantom `Session` per run, implements
   `SimulatedPhysics` over it, and exposes the truth tests use (`lattice_truth`, `sensor_truth`) by today's
   names without computing any of it. Under 300 lines in all; `dot.py` and `noise.py` deleted.
6. The simulated stand built from the device: a DC channel for each gate, pulse channels on the plungers,
   the bias and the sensor; a gate without a channel holds the programmed point.
7. `stability()` and `diamonds()` take their default ranges from the device's programmed point.
8. Run options: the model's scalar fields give way to the noise seed, noise on or off, and the device to
   load (OpenAPI and Flight Deck's help text follow). The cold-sensor scenario becomes a device file
   compiled colder. *As built (ADR 0088):* Phantom 0.2.0 fixes a sensor's peak width whatever the
   temperature, and its default sensor resolves the diamonds, so the cold-sensor scenario became
   `second-device`, a second disorder draw, noise off.
9. The server loads a device once per stand and opens a fresh session per run; the levels view
   (ADR 0057) and the stand state (ADR 0075, 0085) see the same device.
10. Provenance: a simulated run's device record carries the Phantom version, the model versions and the
    device file's SHA-256.
11. Truth never leaves through a server route; tests and committed tune-up results read it.
12. Device files committed under `packages/qdt-sim/src/qdt_sim/devices/` (package data), written only by
    `scripts/make_sim_devices.py`, which compiles them from `qdt_sim/recipes.json` with the pinned Phantom;
    `qdt-sim` refuses a file whose hash does not match its scenario or whose format version Phantom does
    not read (#142).
13. Regenerated once: `packages/qdt-sim/tests/fixtures/stability_24x32.npy`, the seven `SimResult`
    fixtures in `packages/qdt-server/tests/fixtures/`, the schema fixtures, the expectations of tutorials
    02–04; qdt-analysis's injection tests take their truth from Phantom's objects. Step 6c's tests that
    name the simulated stand's channels follow (deliverables 7 and 8, the e2e tests, the L2 rows'
    simulated mode).
14. `python -m phantom.contract packages/qdt-sim/src/qdt_sim/devices/*.json` runs in qdt's CI
    (`scripts/check_all.sh`, beside `make_sim_devices.py --check`).
15. *Found while building (ADR 0088):* the tune-up nodes' windows are the stand's. `qdt_tuning.TEMPLATES`
    take them per node, `Settings.nodes` holds them, and the simulated stand's sit about the device's
    programmed point; tolerances against truth scale with the device.

## L0 tests (CI)
- Interpreter on a stub physics: the level-source and triggered-level-source conformance suites pass
  unchanged; an emitted stage sequence (steps, a measure, a capture on the output, a
  difference, a triggered axis) gives the values the stub physics defines, with the clock advanced as
  the sequence says.
- Before the cutover: the stability fixture and the seven `SimResult` fixtures reproduce bit for bit.
- After: Phantom's contract test passes on every committed device file; the adapter maps the stand onto
  the device's gates; `qdt-sim` holds no physics module and stays under 300 lines; a device file with a
  wrong hash is refused; a simulated record's device carries the Phantom version and the file's hash;
  no truth field appears in the server's OpenAPI document; the tune-up on the simulator reproduces its
  committed scenario outcomes after regeneration; a `SimScenario` v1 (with `model`) is refused.

## L1 tests (bench loopback)
None. The step changes the simulator only; the bench rows of Steps 5–6c run on real instruments through
the same protocols and are unaffected.

## L2 tests (instrument-on-instrument)
None, for the same reason.

## Exit criteria
- Every L0 row above green in CI against the pinned `v0.2.0`, with `qdt-sim` under 300 lines.
- qdt's tune-up on the simulator reproduces its committed scenario outcomes after regeneration
  (Phantom's Step 8 exit, from qdt's side).
- The `SimScenario` change frozen by an ADR.

## Open decisions
- **Settled 2026-10-28 (ADR 0087):** the cutover runs now, beside Step 6c; Phantom pinned by git tag,
  `v0.2.0`, made by the human.
- Held by the human (2026-10-27): the cadence of Phantom releases against qdt's pin (Analysis 0007,
  answer 3). Each pin bump is its own pull request that regenerates the fixtures.
- **Settled (ADR 0088):** a `SimScenario` v1 has no migration. Neither it nor `SimResult` is persisted, the
  only stored v1 objects were the committed fixtures (regenerated), and its overrides have no counterpart.

## Status
DONE in L0 (session 35, 2026-10-28), once its pull request's CI is green against the pinned `v0.2.0`.
Deliverables 1–3 (#141) landed in session 34; deliverables 4–15 (#140, #142) this session, ADR 0088.
`qdt-sim` is 295 lines over Phantom; the seven tune-up fixtures and the stability fixture regenerated, every
tune-up accepted on both committed devices. No L1 or L2 rows.
