# Probe 01: lab guide

This guide covers running Probe 01 on the OPX1000 and the Keysight HD304MSO. It gives the commands,
explains what each step does, and lists what to bring back. Allow about **30 minutes**: the scripts take
about 4 minutes, and the rest is setup. The specification is `docs/probes/01-stream-semantics.md`.

## What this measures, and why it matters
The `Dataset` stream contract is drafted (ADR 0009, 0010) but not frozen. Freezing it needs four answers
that only the hardware can give:

1. **Delivery from the OPX.** How do results arrive: per point, per line, or per frame? Can a partly filled
   buffer be read before it completes?
2. **Sustained rate.** What rate can the OPX → laptop path keep up without losing data?
3. **Changing parameters without recompiling.** Which sweep parameters can change at run time on a
   program that is compiled once?
4. **The scope's time axis.** Does its origin move between captures? If it does, the contract needs a
   separate time axis per record.

Nothing is connected to a device. The OPX programs stream computed numbers and play only zero-amplitude
pulses. The scope captures noise on auto trigger.

## Choosing point rates (already decided; read for context)
The probe does not assume one rate. It measures the whole plausible range. A measurement's own rate is
roughly:

    points/s ≈ 1 / (integration time × number of averages + settle time + overhead)

| Kind of measurement | Cost per point | Points/s |
|---|---|---|
| DC transport, gates stepped by a DC source (ms settle) | 1–10 ms | 10²–10³ |
| RF-reflectometry charge sensing, stepped | 10–100 µs, some averaging | 10⁴–10⁵ |
| Fast "video-mode" maps (OPX sweeps both axes) | 1–5 µs | 2×10⁵–10⁶ |

The script runs **10³, 10⁴, 10⁵, 10⁶ points/s and unpaced** (as fast as the OPX loop goes). Each run lasts
5 s and is done twice: delivering per line and per point. The design target in `docs/FINISH_LINE.md`
is 10⁶ points/s.

## Before the lab day (any machine, no hardware)
**Get the probe code onto `main` and push it.** The lab laptop clones or pulls from GitHub, so these
scripts must be on the remote. At the time of writing they sit on unmerged local branches
(`step-1/flightdeck-benchmark`, `step-1/probe01-scripts`). Merge them and push, and check that CI passes.

Then, from the repo root:
```
uv run --no-project --with qm-qua --with numpy python bench/probes/probe01/opx_probe.py --offline-check
```
Every program should print `ok`, then `offline check passed`. This builds every QUA program and validates
the OPX1000 config without connecting to anything.

## What to bring
- A laptop with the repo and `uv`, on the same network as the OPX1000 and the scope.
- The **OPX1000 host address** and **cluster name**, from the QM web interface or whoever administers it.
- The **QOP version** running on the OPX1000, from the same place.
- The **slot number of an LF-FEM**, and ideally one of its analog outputs with nothing connected.
- The **scope's IP address**. LAN is simpler than USB: USB with the pure-Python VISA backend needs extra drivers.
- **Claude Code** on the laptop, logged in, with internet access. Lab networks sometimes block outbound
  traffic, so check before the day (see below).

## Working with Claude in the lab
Claude can run the probe commands, read the errors and fix the scripts while you watch. Set this up first.

### Starting the session
1. On the lab laptop, get the latest code:
   ```
   cd <path-to>/qdt
   git checkout main && git pull
   uv sync --all-packages
   ```
2. Start Claude Code in the repo root (`claude`, or open the folder in VS Code with the Claude extension).
3. Run `/session-start`. Claude reads `CLAUDE.md` and `docs/STATUS.md`. STATUS.md's next action is the
   Probe 01 lab run, so it should say so and create a branch such as `step-1/probe01-lab`.
4. Paste the opening message below, filling in the blanks you know.

### Opening message (copy, fill in, paste)
```
I'm in the lab at the OPX1000 and the HD304MSO, running Probe 01. Help me run and debug it, following
bench/probes/probe01/LAB_GUIDE.md.

Known so far:
- OPX1000 host: ___   cluster name: ___   QOP version: ___
- LF-FEM slot: ___    analog output to use: ___ (nothing connected: yes/no)
- Scope resource: TCPIP::___::INSTR

How to work:
- Run the guide's commands yourself, one step at a time, and show me each summary.
- Start with the offline check, then --quick. Do the full runs only once --quick is clean.
- When a section fails, read the traceback, inspect the installed qm-qua API (uv run --no-project
  --with qm-qua==<version> python -c ...), fix bench/probes/probe01/*.py, rerun --offline-check, then
  rerun only the failing section (--sections ...).
- Hardware rules: run only the probe scripts. Never play a non-zero amplitude or change any output other
  than the agreed LF-FEM port. Ask me before anything that would open another quantum machine, change the
  OPX config beyond the probe's, or send SCPI commands not in scope_probe.py.
- Don't change production code (packages/, apps/) today. Probe scripts and docs only.
- Commit script fixes as fix(bench): ... and results as bench: Probe 01 results. At the end, fill the
  Findings table in docs/probes/01-stream-semantics.md from the printed summaries and rewrite STATUS.md.
```

### Tips while debugging
- **Prefer the quick loop.** `--quick` plus `--sections <name>` reruns one section in seconds. Full runs
  take ~2 minutes each.
- **Paste whole tracebacks.** If you run something outside Claude, paste the full output, not a summary.
  Version-specific API names are usually visible only in the traceback.
- **Record versions early.** The OPX script prints `qm-qua` and the server version first. Make sure they
  go into the results.
- **Partial results are fine.** If time runs out, commit what you have, including failures. The next
  session can finish from the JSON files.
- **If the laptop can't reach Claude** (blocked network), run the commands yourself and commit the outputs.
  Afterwards, start a session anywhere and say: "Probe 01 results are in bench/fixtures/probe01; some
  sections failed — read opx_findings.json and fix the scripts."

## Steps
Run everything from the repo root. Replace `X.Y.Z` with the `qm-qua` version, `<ip>` with the host,
`<name>` with the cluster name and `<slot>` with the LF-FEM slot.

**1. Pick the `qm-qua` version.** Start with the latest. If connecting in step 3 reports an incompatible
server, use the version QM documents for your QOP release. `--no-project` keeps this install separate from
the repo's own dependencies.

**2. Offline check with that version.**
```
uv run --no-project --with qm-qua==X.Y.Z --with numpy python bench/probes/probe01/opx_probe.py --offline-check
```

**3. Dry run (~10 s).** This checks the connection, the FEM slot and the result APIs on short runs.
```
uv run --no-project --with qm-qua==X.Y.Z --with numpy python bench/probes/probe01/opx_probe.py \
    --host <ip> --cluster <name> --fem <slot> --quick --out bench/fixtures/probe01/quick
```
It prints the environment (`qm-qua` and server version), then each section. A failing section prints a
traceback and the others continue. Fix any failure before the full run (see "If something fails").

**4. Full OPX run (~2 minutes).**
```
uv run --no-project --with qm-qua==X.Y.Z --with numpy python bench/probes/probe01/opx_probe.py \
    --host <ip> --cluster <name> --fem <slot> --out bench/fixtures/probe01
```
To use an output other than 1 on the LF-FEM, add `--ao <n>`. The probe sets that output's DC offset to
0 V and plays only zero-amplitude 16 ns pulses on it.

**5. Scope run (~2 minutes).**
```
uv run --no-project --with pyvisa --with pyvisa-py python bench/probes/probe01/scope_probe.py \
    --resource "TCPIP::<scope-ip>::INSTR" --out bench/fixtures/probe01
```
The last lines should read `instrument errors: none`. Any error listed names the SCPI command the scope
rejected.

**6. Commit the results.**
```
git add bench/fixtures/probe01
git commit -m "bench: Probe 01 results"
```
That commits the timing CSVs plus `opx_findings.json` and `scope_findings.json`. You can paste the printed
summaries into the Findings table of `docs/probes/01-stream-semantics.md` now, or leave that for the next
session.

## What a good run looks like
- **OPX summary:** one line per ladder run (`lines_1e+03` … `points_unpaced`) with delivered points/s,
  inter-arrival times, fetch cost per point, `dataloss False` and `complete True`, at least at the lower
  rates.
- **Data loss at the top of the ladder is a finding, not a failure.** It marks the ceiling of the
  OPX → laptop path.
- **Last OPX lines:** whether a whole-frame buffer showed anything early, whether input streams and IO1
  changed parameters without recompiling, and the cost of a timestamp stream.
- **Scope summary:** one line per record length (10³–10⁶) with acquisition and transfer times, frames per
  second, and the **time-axis origin spread in samples**. That last number answers question 4.

## If something fails
| Symptom | Likely cause | What to do |
|---|---|---|
| Connection error or "incompatible" message at start | `qm-qua` doesn't match QOP | Use the `qm-qua` version QM lists for your QOP release |
| `bad config`, or an error naming a port or FEM | Wrong slot, or that slot isn't an LF-FEM | Check slots in the QM web interface; pass the right `--fem` / `--ao` |
| `AttributeError` in one section (e.g. `set_io1_value`, `add_to_queue`, `count_so_far`) | API name differs in your `qm-qua` version | The other sections still run. Note the error; the next session adapts the script |
| A ladder run shows `complete False` | Run hit its timeout | Note the rate. That is useful information about the ceiling |
| Scope: `instrument error after ':WAVeform:POINts:MODE RAW'` or similar | Firmware spells that command differently | The rest still runs. Note the error |
| Scope hangs for 30 s per capture | Auto trigger wasn't accepted | Check that `:TRIGger:SWEep AUTO` shows no error; set auto trigger on the front panel and rerun |
| `VISA backend` / resource not found | No vendor VISA installed and USB in use | Use the LAN resource string, or install Keysight IO Libraries |

If a section fails and you can't fix it on the spot, commit what you have. Partial results plus the error
text in `opx_findings.json` are still enough for the next session to adapt the script.

## What is and isn't verified in advance
- **Verified without hardware:** every QUA program and the OPX1000 config. The offline check passes with
  `qm-qua` 1.4.1, and a deliberately broken config makes it fail.
- **Only checkable on the day:** run-time APIs (result handles, pushing input values, pause/resume, IO1)
  and the scope's SCPI commands. That is why the dry run comes first, and why every section is isolated.

## What happens next
A session on `step-1/contract-freeze` reads `bench/fixtures/probe01/`, fills in the Findings table, checks
ADR 0009/0010 against it, and writes the contract-freeze ADR. That closes Step 1.
