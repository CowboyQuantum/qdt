# 0088 — `qdt-sim` is an adapter over Phantom `v0.2.0`: committed device files pinned by hash, a scenario names one, the stand and its tune-up windows come from the device

**Status:** Accepted
**Date:** 2026-10-28
**Step:** 6d (deliverables 4–14; issues #140, #142)

## Context
ADR 0087 placed the cutover and fixed its frame: Phantom is a dependency of `qdt-sim` alone, pinned by
git tag, reached through `phantom.api`, behind qdt-lab's `SimulatedPhysics` protocol (#141 moved the
sequencer interpreter there). This ADR records what the cutover itself decided, against Phantom `v0.2.0`
(`f72daac`) as measured on 2026-10-28 with its textbook two-dot SiGe layout at an 80 nm pitch, programmed
at 0.6 V on the plungers and the sensor gate:

| Quantity | qdt-sim's model | Phantom device, draw 2 |
|---|---|---|
| Gates | `P1`, `P2`, `SG` | `B_L`, `P1`, `B_M`, `P2`, `B_R`, `SG`, `R_L`, `R_R` |
| Charge lattice (electrons per volt, diagonal) | about 75 | 19.2 and 24.7 |
| Electrons on the dots at the programmed point | about 0 near 0 V | 20 and 25 |
| Sensor gate's lever arm on the sensor potential | 1.0 | 0.25 |
| Sensor peak period and width in sensor-gate volts | 0.25 V and 0.04 V | 1.0 V and 0.16 V |
| Readout noise | 15 pA whatever the integration | 15 pA × √(1 ms / dwell): 336 pA at 2 µs |
| Wall time of one `sense` call | about 0.02 ms | 0.6 ms without charge dynamics, 3.8 ms with |

So the tune-up's node windows, written for qdt-sim's toy device (plungers 0.03–0.18 V, the sensor gate
±0.2 V, 2 µs a pixel), cannot find this device: a 2 µs pixel is all noise, and the windows hold too few
transitions and less than one sensor period. With windows sized to the device and 10 ms a lattice pixel,
a prototype ran all four nodes on both devices and accepted them: the lattice's diagonal within 0.5 %,
the virtual lattice's residual cross ratios within 0.005, and the sensor's peak, period, charging energy,
lever arm, width and wing inside the existing tolerances.

Two things the plan expected are not so in `v0.2.0`. A sensor's peak width is fixed at 0.04 V of sensor
potential whatever the compile temperature, so "the cold-sensor scenario becomes a device file compiled
colder" (step file, deliverable 8) has nothing to compile. It is not needed either: the diamonds method
resolves this device's warm sensor. And Phantom's noise is physical, so the wing node's peak fit (its window search between the smoothed
trace's minima) does not survive it; on qdt-sim the sensor scenario ran with noise off for the same kind
of reason.

## Decision
1. **Device files.** Phantom's canonical JSON, committed in `packages/qdt-sim/src/qdt_sim/devices/`
   (package data, so an installed `qdt-sim` carries them), their recipes in `qdt_sim/recipes.json`, and
   written only by `scripts/make_sim_devices.py`, which compiles every recipe with the pinned Phantom
   (`--check`, in `check_all`, recompiles and compares). Two devices for
   now, one layout and one programmed point: `two-dot-sige-a` (disorder draw 2, the default) and
   `two-dot-sige-b` (draw 5). `qdt_sim.scenarios.DEVICES` pins each file's SHA-256; `load_device` refuses
   a name it does not list, a file that hashes otherwise, and a format the pinned Phantom does not read.
2. **`SimScenario` v2** (`schema_version` 2) names a device by `device` and `device_sha256`; `seed` is the
   noise seed only (the disorder is in the file); `model` is gone. Neither `SimScenario` nor `SimResult` is
   persisted (`migrations.PERSISTED`), so there is no migration: the only stored v1 objects were the
   committed `SimResult` fixtures, regenerated here. A v1 object is refused on load (an unknown `model`
   field); its overrides referred to a model that no longer exists.
3. **The adapter.** `PhantomPhysics` is one Phantom `Session` per run: inputs are the device's gates and
   `bias` (the sensor's source–drain voltage, default Phantom's 50 µV), the output is `sensor`; each input
   defaults to the programmed point, so a gate without a channel holds it. Charge dynamics are off: each
   sample's charge is an independent Boltzmann draw (qdt-sim's behaviour), six times cheaper. A shot's
   overhead is a `hold` before its reading. The noise seed is a run option; the device's own noise
   realisation is never replayed. `qdt-sim` keeps no physics and stays under 300 lines; its
   `python -m qdt_sim` stream is retired, since `python -m qdt_server` streams the same stand to Flight Deck.
4. **The stand from the device**: a DC channel per gate, a pulse channel on each plunger (`P1_pulse`,
   `P2_pulse`, from the knowable layout's roles), `bias` and `bias_pulse`, and `sensor`. The stand id and
   the channel names the tune-up nodes use are unchanged.
5. **Sweeps about the programmed point.** `stability()` steps P1 ±0.15 V about its programmed level and
   pulses P2 ±0.15 V about its DC level (a pulse adds to the DC level, so a pulse window is relative);
   `diamonds()` steps the sensor gate from 1.2 V below to 0.8 V above its programmed level. Both now build
   on qdt-tuning's `stability_diagram` and `coulomb_diamonds`, so `qdt-sim` depends on `qdt-tuning`. A
   stability pixel integrates 1 ms.
6. **Tune-up windows are the stand's.** `qdt_tuning.TEMPLATES` take, beside the sequencer and the sensor
   gate, keyword windows per node; the server's `Settings.nodes` holds them per node id. The simulated
   stand's (`qdt_server.app.SIMULATED_NODES`) sit about the default device's programmed point: plungers as
   in `stability()` with 64 pixels a side at 10 ms each, the sensor diamonds as in `diamonds()`, the flank
   offset 0.1 V (the wing is 0.105 V above the peak), the wing window ±0.4 V. A real stand (`--stand`)
   gives none, so its nodes keep the constructors' defaults until the bench chooses its own.
7. **Scenarios.** `default-occupied-window` (device a, noise on, noise seed 1) and `default-quiet` (device a,
   noise off) keep their roles. `cold-sensor` becomes `second-device`: device b, noise off, the full
   four-node chain, so the tune-up is shown on a disorder draw it was not shaped on. The fixture names
   follow (`*_second`).
8. **Truth.** `lattice_truth` and `sensor_truth` rename `Device.truth()`'s fields and compute nothing; the
   sensor's peak is the one nearest the programmed sensor gate unless a voltage is given. Truth never
   leaves through a server route.
9. **Tolerances against truth scale with the device.** The lattice's cross terms are compared
   absolutely, within 0.2 electrons per volt (a quarter of the power spectrum's bin over a 0.3 V window),
   not within 4 %: they are about 2 e/V here, and a relative bound on a small number measures the
   spectrum's resolution rather than the method. The sensor's peak and operating point are compared
   within 0.02 V, an eighth of its 0.16 V peak width (the old 5 mV was half the width of qdt-sim's cold
   10 mV peak). Its period within 5 % and its lever arm within 10 %: the 2 V diamond window charges each
   dot by about one electron through the sensor gate's cross capacitance (4.6 meV per volt against a 10
   meV addition energy), which moves the sensor by about 4 % of a period, while Phantom's truth holds the
   dots' charge fixed; device b measures 3.1 % and 6.7 %. Every other tolerance stands.
10. **Provenance.** The simulated `DeviceRecord` carries `phantom_version`, `device_file`, `device_sha256`
    and every `phantom.<module>` model version (`qdt_sim.scenarios.provenance`). A registry keeps the first
    record for an id, so a registry that outlives a pin bump keeps the first pin's attributes; records
    made by a run carry the run's options (which name the device when a run picks one) in the run.
11. **The contract runs in qdt's CI.** `scripts/check_all.sh` runs `python -m phantom.contract` on every
    committed device file, so a pin bump that a device file no longer satisfies fails before any fixture.
12. **ADR 0020 is superseded** by this one for its model and noise; its other decision, one simulated
    device behind the capability protocols, lives on in `qdt_lab.simulated.SimulatedInstrument`.

## Consequences
- Easier: qdt's simulator is Phantom's eight-gate device with disorder, wiring, physical noise and a sensor
  that sits where the electrostatics put it; a pin bump changes physics with one script and two
  regenerations; tune-up windows are stand data, which the bench needed anyway.
- Harder: the simulator is about thirty times slower per reading, so simulated sweeps are smaller (64 a
  side) and the test suite takes longer; every simulator fixture and every test that named qdt-sim's
  model changed once; a scenario cannot vary one parameter of a device, only pick a compiled device.
- Must now: a new device is a recipe plus `make_sim_devices.py` plus its hash in `DEVICES`; a pin bump is
  its own pull request (ADR 0087) that runs that script, the two fixture scripts and updates the hashes.

## Alternatives considered
- Keep the nodes' windows and choose a recipe that fits them — rejected: the sensor gate's lever arm is set
  by the geometry (0.25 here, never qdt-sim's 1.0), so no recipe puts two sensor peaks in ±0.2 V.
- Change qdt-tuning's default windows to the simulator's — rejected: the defaults would then describe one
  simulated device, and the bench would inherit them silently.
- Windows relative to the held level through `InputBinding.held` — rejected: a binding needs an upstream
  node, and the first nodes have none.
- Charge dynamics on — rejected for now: 3.8 ms a reading, and at the devices' gigahertz tunnel rates a
  microsecond dwell sees the equilibrium anyway. A run option can add it when a sweep needs latching.
- A migration from `SimScenario` v1 — rejected: nothing persisted holds one, and its overrides have no
  counterpart.
