# Run the simulated stand and drive it from Flight Deck

This guide starts qdt's simulated stand on your own computer and walks through controlling it from Flight
Deck, qdt's browser front end. By the end you will have:
- measured a stability diagram and found its charge transitions;
- measured the charge sensor's Coulomb diamonds;
- moved the operating point;
- run the four-node tune-up.

Nothing here needs an instrument. The stand runs the same server, the same run queue and the same
registry as the bench, so what you learn here carries over to a real stand.

## What the simulated stand is

The stand is one simulated instrument wired to a simulated device. The device comes from
[Phantom](https://github.com/CowboyQuantum/phantom), a separate simulator of gate-defined quantum dots that
qdt pins at version `v0.2.0` (ADR 0087, ADR 0088). It is a silicon–germanium double dot with a charge
sensor:

- **Eight gates.** The plungers `P1` and `P2` set each dot's energy. The barriers `B_L`, `B_M` and `B_R`
  separate the dots from each other and from the leads. The reservoir gates `R_L` and `R_R` fill the
  leads. The sensor gate `SG` tunes the charge sensor. Every gate starts at the device's programmed point:
  0.6 V on `P1`, `P2` and `SG`.
- **Two pulse lines,** `P1_pulse` and `P2_pulse`. A pulse adds to its gate's direct-current (DC) level,
  as a bias tee does.
- **The sensor's source–drain bias,** `bias`, which starts at 50 µV, with its own pulse line `bias_pulse`.
- **The sensor,** whose current (in amperes) is what every measurement reads.
- **A simulated oscilloscope,** `scope` on channel `scope1`, for time-resolved captures.

The device is physical rather than a toy. About 20 electrons sit on each dot at the programmed point, each
dot gains one electron for every 40 to 50 mV on its plunger, and the sensor's peaks are about 1 V apart on
`SG`. The readout noise is realistic too: it falls as the square root of the integration time, so a 2 µs
reading is mostly noise and a 1 ms reading is clean. Two devices are committed: `two-dot-sige-a`, the
default, and `two-dot-sige-b`, a second disorder draw of the same design.

## Before you start

You need:
- [uv](https://docs.astral.sh/uv/), which installs the right Python and every package;
- [Node.js](https://nodejs.org/) 20 or newer, which comes with `corepack`, to build Flight Deck;
- a clone of this repository, with network access to GitHub the first time, because `uv` fetches
  Phantom from its repository.

Install everything from the repository's root:

```bash
uv sync --all-packages --all-extras
```

## Start the stand

### The quick way: one command

```bash
uv run python scripts/demo_control_path.py
```

This builds Flight Deck the first time (it needs `corepack`), starts the stand server against the
simulated device, serves Flight Deck from the same server and opens your browser at
<http://127.0.0.1:8700/>. It prints a short walkthrough of this guide. Stop it with Ctrl+C.

Useful options:
- `--root <folder>` keeps the records in another registry, for example a throwaway folder. The default
  is `~/.qdt/registry`.
- `--rebuild` rebuilds Flight Deck after you change its code.
- `--no-browser` does not open a browser.

### The development way: two terminals

Use this when you are changing Flight Deck, because Vite reloads the page on every save.

```bash
# terminal 1, at the repository's root: the stand server
uv run python -m qdt_server

# terminal 2: Flight Deck (run pnpm from apps/flightdeck so corepack uses the pinned version)
cd apps/flightdeck
corepack pnpm install
corepack pnpm dev
```

Open the address Vite prints, normally <http://localhost:5173/>. Flight Deck finds the server by itself:
- its application programming interface (API) at `http://127.0.0.1:8700`;
- its data stream at `ws://127.0.0.1:8765`.

If you moved either one, add `?api=…` or `?ws=…` to Flight Deck's address.

Either way, the server's interactive API documentation is at <http://127.0.0.1:8700/docs>.

## The workspace

![Flight Deck's workspace on the simulated stand](img/01-workspace.png)

- **The top strip** names the stand (`simulated-double-dot`) and the device (`dot`), shows the stream's
  state and the next run, and holds the one **Run** button.
- **The left column** holds **Sweep** (what to measure), **Analysis** (a method on a stored record) and
  **Tune-up** (the calibration nodes).
- **The centre** holds the plots. Each plot follows the live stream or is pinned to one record. Its ⚙
  menu chooses the variable, a transform such as the derivative, and a line cut.
- **The right column** holds:
  - **Pulse**, the sequence each shot plays;
  - **Levels**, every channel's setpoint, held level and readback;
  - **Queue**, the stand's run queue;
  - **History**, the stored records.

Each pane's title is a menu, so any pane can show any widget. The `+` button adds a pane below and `✕`
closes it. The layout is remembered in your browser.

> **Watch the default window.** The Sweep form opens at 0.03 to 0.18 V on both axes with a 2 µs reading.
> Those values suited qdt's earlier toy simulator. On this device they land far from where the electrons
> are, and the reading is mostly noise. Use the values below instead.

## 1. Measure a stability diagram

A stability diagram steps `P1` on its DC line and pulses `P2` inside each shot. The sensor's current
changes in a step each time a dot gains an electron, which draws the honeycomb of charge transitions.

In **Sweep**:
1. Leave **kind** at `stage: inner axis pulsed`, and name the sweep.
2. Set the **outer** axis to `P1` from `0.45` to `0.75` with `48` points: 0.15 V either side of its
   programmed 0.6 V.
3. Set the **inner** axis to `P2_pulse` from `-0.15` to `0.15` with `48` points. These are offsets,
   because the pulse adds to `P2`'s 0.6 V DC level.
4. Set **options** to `{"seed": 1, "noise": false}`. With noise off, the template's 2 µs reading is
   enough. To measure with noise on, change the `measure` row's **duration** in **Pulse** to `1000000`
   (1 ms) or more.
5. Press **compile**. The plan box shows what the server will do. On this stand the device triggers the
   `P1` axis itself, so no marker line is needed.

![The Sweep form for a stability diagram](img/02-sweep-form.png)

Press **Run** in the top strip. The sweep joins the stand's queue, runs, and draws live in the plot. When
the strip says `completed → record …`, the record is in the registry.

![The stability diagram, measured live](img/03-stability.png)

The steps sit on top of a strong slope, because the plungers also move the sensor. Choose the derivative
in the plot's ⚙ menu to make the transitions stand out.

## 2. Find the charge transitions

1. In **History**, press **refresh**, then **analyse** on the new record. This selects it in Analysis.
2. In **Analysis**, choose the method **Charge transitions** and press **run analysis**.
3. Press **show overlays** to replay the record with the detected segments drawn on it. Press **show
   output** to see the map the method detected on.

![The detected transitions drawn on the map](img/04-transitions.png)

The estimates are electrons per volt on each dot from each plunger. On the default device they come out
near 19.3 and 24.8 on the diagonal, which is the device's own lattice within half a percent. The result
is stored with the record, and the method's name, version and every parameter are kept with it.

## 3. Measure the sensor's Coulomb diamonds

The diamonds give the sensor's charging energy, peak spacing and lever arm. This is a DC sweep: both axes
are stepped from the host, and the sensor is read at every point.

In **Sweep**:
1. Set **kind** to `DC: both axes stepped, sensed`, and name the sweep.
2. Set the **outer** axis to `SG` from `-0.6` to `1.4` with `64` points. That is two sensor peaks about
   `SG`'s programmed 0.6 V.
3. Set the **inner** axis to `bias` from `-0.0015` to `0.0015` with `64` points, and set **inner axis
   name** to `V_sd`.
4. Keep **sensor** at `sensor`, and set **options** to `{"seed": 1, "noise": false}`.

Press **Run**. Then analyse the record with **Coulomb diamonds** and **show overlays**.

![The sensor's Coulomb diamonds with the detected edges](img/05-diamonds.png)

The default device gives a charging energy of 1.0 meV and a peak spacing of about 0.98 V on `SG`.

## 4. Move the operating point

The stand holds an operating point: a level for each channel that every later sweep inherits unless the
sweep moves that channel itself.

- **In Levels**, type a value in a channel's box and press **set**. The value is applied and held.
  **release** forgets the held point and leaves the stand where it is.
- **On a map**, click a point, and Levels offers the clicked coordinates as levels to set. This is right
  for `P1` on its DC line. On a pulsed axis it currently sets the gate's DC level to the pulse offset, not
  to the voltage you clicked; issue #150 tracks it. Set `P2` in Levels instead.
- **In a sweep**, **add level** holds a channel for that sweep alone.

![The Levels widget, with the sensor gate held where the tune-up parked it](img/08-levels.png)

A limit on a channel (set in Levels, with a reason) makes the server refuse every level and every sweep
that would cross it, rather than clamp it. Each change is a new, versioned stand state.

## 5. Run the tune-up

The tune-up runs four calibration nodes in order on the server. Each node's sweep is an ordinary run on
the stream, so you can watch it:
- **sensor-operating-point** finds the sensor's peaks from its diamonds;
- **sensor-wing** fits one peak and parks `SG` on its steepest flank;
- **charge-lattice** measures the stability diagram and decides the virtual-gate matrix;
- **virtual-lattice** measures again in virtual gates and checks that the transitions come out straight.

In **Tune-up**, leave the four nodes ticked, set **options** to `{"seed": 2, "noise": false}` and press **run
tune-up**. The sensor nodes need noise off, because their peak fit does not survive the device's noise.
The node windows come from the server and already suit the device. The whole tune-up takes about 20
seconds.

![The tune-up's four nodes, all accepted](img/07-tuneup-result.png)

When it completes, every node is accepted. The server holds `SG` at the wing it found, and the last plot
is the stability diagram in virtual gates.

![The stability diagram in virtual gates, after the tune-up](img/06-tuneup.png)

## Run options

**options** in Sweep and Tune-up is a small JSON (JavaScript Object Notation) object. On the simulated
stand it takes:

| Option | What it does |
|---|---|
| `seed` | The noise seed: the same seed gives the same noise, another seed a new realisation. The device's own disorder is fixed by its file. |
| `noise` | `true` or `false`: whether the device's noise is on. |
| `device` | Which committed device to load: `two-dot-sige-a` (the default) or `two-dot-sige-b`. Any other name fails the run. |
| `campaign` | A label kept on the record, to find it later. |
| `tau_s`, `droop_v`, `scope_noise_v` | The simulated scope's recorded droop: its time constant in seconds, its step in volts and its noise in volts. |

## The queue, the records and starting again

- **Run** adds the sweep to the stand's queue. In **Queue** you can move or remove a waiting entry, abort
  the running one, or pause the queue. An aborted run keeps what it streamed, recorded as aborted.
- Every completed run is a record in the registry: by default `~/.qdt/registry`, or the folder `--root`
  names. **History** lists the records, and **open** shows one in a new plot.
- Restarting the server keeps every record. It offers the held operating point again in Levels, and
  nothing is re-applied until you press **re-apply**.
- To start from nothing, stop the server and start it with a new, empty folder as `--root`.

## When something looks wrong

| What you see | Why, and what to do |
|---|---|
| The map is speckled noise. | The reading is too short for the noise. Set `"noise": false`, or raise the `measure` duration in Pulse to 1 ms or more. |
| The map is a smooth slope with no steps. | The window is away from the electrons, probably the 0.03–0.18 V default. Sweep about 0.6 V as in step 1. |
| Flight Deck shows no stand, or every command fails. | The server is not running, or it is on another port. Start `python -m qdt_server`, or pass `?api=` and `?ws=` in Flight Deck's address. |
| `address already in use` when starting. | Another server is running. Stop it, or start this one with `--port` and `--stream-port`. |
| A command from another computer is refused. | Commands from another computer need a token. Run `uv run python -m qdt_server --add-token "<desk>"`, start the server with `--host 0.0.0.0`, and open Flight Deck there with `?token=<token>` once. |
| A sweep is refused with "would reach". | A limit on that channel forbids it. Change the sweep, or remove the limit in Levels. |

## Going further

- [Tutorials](../tutorials/README.md) do the same things from Python scripts, and CI runs them.
- [The Phantom cutover](../steps/06d-phantom-cutover.md), ADR 0087 and ADR 0088 explain how the simulator
  is built and pinned.
- On the bench, the same server runs real instruments: `python -m qdt_server --stand stand.json
  --device-id <id>` (see [BENCH.md](../BENCH.md)). Flight Deck does not change.
