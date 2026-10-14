"""Probe 02 — OPX1000 LF-FEM input calibration (docs/probes/02-opx-input-calibration.md).

Cable: LF-FEM analog output 1 → LF-FEM analog input 1 (the same cable the L1 pulse row used into the
scope, where the 0.25 V pulse measured 253.9 mV; the scope factor `--scope-gain` carries that in).

One QUA program plays a constant pulse of known amplitude on the output and, in the same shot, reads the
input two ways: the raw ADC trace and the integrated value over a window on the plateau. Repeated for a
few amplitudes, including zero (the input offset). From the fits:

    RAW_ADC_TO_VOLTS      volts per raw ADC unit        (slope of volts vs raw plateau mean)
    INTEGRATION_TO_VOLTS  mean volts = I * K / window   (K from volts * window_ns / I)
    time of flight        pulse edge position in a readout aligned with the play

Usage: python opx_calibration.py --host <qm-host> [--fem 1] [--out bench/fixtures/probe02]
Mirrors the driver's config (direct output mode, sticky off here, time_of_flight 24, smearing 0).
Everything lands in --out as JSON; the summary at the end goes into the probe doc's Findings.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

CONTROLLER = "con1"
PULSE_NS = 3000
WINDOW_NS = 1000
WINDOW_DELAY_NS = 1000
TIME_OF_FLIGHT_NS = 28  # the QOP minimum; --tof overrides to check where the edge lands
REF_AMPLITUDE_V = 0.25
AMPLITUDES_V = (0.25, 0.1, 0.0, -0.1, -0.25)
SHOTS = 20


def config(fem: int, tof: int = TIME_OF_FLIGHT_NS) -> dict:
    return {
        "version": 1,
        "controllers": {
            CONTROLLER: {
                "type": "opx1000",
                "fems": {
                    fem: {
                        "type": "LF",
                        "analog_outputs": {1: {"offset": 0.0, "output_mode": "direct"}},
                        "analog_inputs": {1: {"offset": 0.0}},
                    }
                },
            }
        },
        "elements": {
            "ao": {
                "singleInput": {"port": (CONTROLLER, fem, 1)},
                "intermediate_frequency": 0,
                "operations": {"pulse": "pulse"},
            },
            "ai": {
                "singleInput": {"port": (CONTROLLER, fem, 1)},
                "intermediate_frequency": 0,
                "operations": {"window": "window", "edge": "edge"},
                "outputs": {"out1": (CONTROLLER, fem, 1)},
                "time_of_flight": tof,
                "smearing": 0,
            },
        },
        "pulses": {
            "pulse": {
                "operation": "control",
                "length": PULSE_NS,
                "waveforms": {"single": "ref_wf"},
            },
            "window": {
                "operation": "measurement",
                "length": WINDOW_NS,
                "waveforms": {"single": "zero_wf"},
                "integration_weights": {"const": "w_window"},
                "digital_marker": "ON",
            },
            "edge": {
                "operation": "measurement",
                "length": PULSE_NS,
                "waveforms": {"single": "zero_wf"},
                "integration_weights": {"const": "w_edge"},
                "digital_marker": "ON",
            },
        },
        "waveforms": {
            "ref_wf": {"type": "constant", "sample": REF_AMPLITUDE_V},
            "zero_wf": {"type": "constant", "sample": 0.0},
        },
        "digital_waveforms": {"ON": {"samples": [(1, 0)]}},
        "integration_weights": {
            "w_window": {"cosine": [(1.0, WINDOW_NS)], "sine": [(0.0, WINDOW_NS)]},
            "w_edge": {"cosine": [(1.0, PULSE_NS)], "sine": [(0.0, PULSE_NS)]},
        },
    }


def _adc_stream(qua):
    import inspect

    if (
        hasattr(qua, "declare_output_stream")
        and "adc_trace" in inspect.signature(qua.declare_output_stream).parameters
    ):
        return qua.declare_output_stream(adc_trace=True)
    return qua.declare_stream(adc_trace=True)


def program(shots: int):
    """Per amplitude: `shots` repeats of [play the pulse on ao | after WINDOW_DELAY, a WINDOW_NS measure
    on ai saving the raw trace and the integral]; then one aligned PULSE_NS readout for the edge."""
    from qm import qua

    scales = [a / REF_AMPLITUDE_V for a in AMPLITUDES_V]
    with qua.program() as prog:
        k = qua.declare(int)
        s = qua.declare(qua.fixed)
        i_val = qua.declare(qua.fixed)
        adc = _adc_stream(qua)
        i_st = qua.declare_stream()
        edge = _adc_stream(qua)
        with qua.for_each_(s, scales):
            with qua.for_(k, 0, k < shots, k + 1):
                qua.align("ao", "ai")
                qua.play("pulse" * qua.amp(s), "ao")
                qua.wait(WINDOW_DELAY_NS // 4, "ai")
                qua.measure("window", "ai", adc, qua.integration.full("const", i_val, "out1"))
                qua.save(i_val, i_st)
                qua.wait(500, "ao", "ai")
        qua.align("ao", "ai")
        qua.play("pulse", "ao")
        qua.measure("edge", "ai", edge)
        with qua.stream_processing():
            adc.input1().save_all("adc")
            i_st.save_all("I")
            edge.input1().save_all("edge")
    return prog


def fetch(job) -> dict[str, np.ndarray]:
    h = job.result_handles
    h.wait_for_all_values()
    out = {}
    for name in ("adc", "I", "edge"):
        v = h.get(name).fetch_all()
        out[name] = np.asarray(v["value"] if v.dtype.names and "value" in v.dtype.names else v)
    return out


def analyse(raw: dict[str, np.ndarray], scope_gain: float, shots: int, tof: int) -> dict:
    n_amp = len(AMPLITUDES_V)
    adc = raw["adc"].reshape(n_amp, shots, -1).astype(np.float64)
    integ = raw["I"].reshape(n_amp, shots).astype(np.float64)
    true_v = np.array(AMPLITUDES_V) * scope_gain
    raw_mean = adc.mean(axis=(1, 2))
    raw_std = adc.mean(axis=2).std(axis=1)
    i_mean = integ.mean(axis=1)
    i_std = integ.std(axis=1)
    slope_raw, off_raw = np.polyfit(raw_mean, true_v, 1)
    slope_i, off_i = np.polyfit(i_mean, true_v, 1)
    resid_raw = true_v - (slope_raw * raw_mean + off_raw)
    resid_i = true_v - (slope_i * i_mean + off_i)
    e = np.asarray(raw["edge"], dtype=np.float64).reshape(-1)
    if e.ndim == 1 and e.size > PULSE_NS:
        e = e[:PULSE_NS]
    half = (e[-200:].mean() + e[:5].mean()) / 2 if e.size else 0.0
    above = np.flatnonzero(e >= half) if raw_mean[0] >= raw_mean[-1] else np.flatnonzero(e <= half)
    edge_ns = int(above[0]) if above.size else None
    return {
        "amplitudes_v_set": list(AMPLITUDES_V),
        "amplitudes_v_true": true_v.tolist(),
        "raw_plateau_mean": raw_mean.tolist(),
        "raw_plateau_shot_std": raw_std.tolist(),
        "integral_mean": i_mean.tolist(),
        "integral_shot_std": i_std.tolist(),
        "RAW_ADC_TO_VOLTS": float(slope_raw),
        "raw_offset_v_at_zero_raw": float(off_raw),
        "raw_zero_input_offset_raw": float(raw_mean[AMPLITUDES_V.index(0.0)]),
        "INTEGRATION_TO_VOLTS": float(slope_i * WINDOW_NS),
        "integral_offset_v": float(off_i),
        "fit_residual_max_mv": {
            "raw": float(np.abs(resid_raw).max() * 1e3),
            "integral": float(np.abs(resid_i).max() * 1e3),
        },
        "window_ns": WINDOW_NS,
        "assumed": {"RAW_ADC_TO_VOLTS": 2.0**-12, "INTEGRATION_TO_VOLTS": 2.0**12},
        "edge_index_ns_in_aligned_readout": edge_ns,
        "configured_time_of_flight_ns": tof,
        "shots": shots,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--cluster-name", default=None)
    p.add_argument("--fem", type=int, default=1)
    p.add_argument("--shots", type=int, default=SHOTS)
    p.add_argument(
        "--tof", type=int, default=TIME_OF_FLIGHT_NS, help="time_of_flight to configure (ns)"
    )
    p.add_argument(
        "--scope-gain",
        type=float,
        default=253.9 / 250.0,
        help="scope-measured over set amplitude for this output (L1 row 3)",
    )
    p.add_argument("--out", type=Path, default=Path("bench/fixtures/probe02"))
    a = p.parse_args()
    from qm import QuantumMachinesManager

    kw = {"host": a.host}
    if a.port:
        kw["port"] = a.port
    if a.cluster_name:
        kw["cluster_name"] = a.cluster_name
    qmm = QuantumMachinesManager(**kw)
    qm = qmm.open_qm(config(a.fem, a.tof), close_other_machines=True)
    try:
        job = qm.execute(program(a.shots))
        raw = fetch(job)
    finally:
        qm.close()
    a.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out / f"opx_calibration_tof{a.tof}_raw.npz", **raw)
    findings = analyse(raw, a.scope_gain, a.shots, a.tof)
    (a.out / f"opx_calibration_tof{a.tof}.json").write_text(json.dumps(findings, indent=2))
    print(json.dumps(findings, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
