"""DMM measurement sequence for a battery health check.

Uses only the DMM. Nothing here drives current into or out of the battery.
"""
import csv
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from .dmm import Dmm
from .analysis import OPEN_NOISE_V, PRESENT_V, Assessment, Measurement, dominant_frequency


RIPPLE_RANGE_V = 0.05
MAX_SCOPE_RATE = 1.8e6                 # PXIe-4082 maximum waveform rate
SCOPE_WINDOW_S = 0.055                 # covers the 50 ms ripple plot


@dataclass(frozen=True)
class TestSettings:
    dc_readings: int = 10
    dc_digits: float = 6.5
    ripple_readings: int = 2
    wave_rate: float = 10_000.0
    wave_points: int = 10_000          # 1 s at 10 kS/s: 1 Hz frequency resolution
    scope_rate: float = MAX_SCOPE_RATE # high-rate capture used only for the ripple plot


def quick_read(dmm: Dmm) -> float:
    """DC reading for live monitoring (~0.3 s). 6.5 digits integrates over whole
    power-line cycles, so open leads read near 0 V instead of wandering with mains pickup."""
    dmm.configure_dc_volts(range_v=10.0, digits=6.5)
    return dmm.read()


def run_test(dmm: Dmm, s: TestSettings = TestSettings(),
             progress: Callable[[str], None] = lambda msg: None) -> Measurement:
    progress("Measuring DC voltage…")
    dmm.configure_dc_volts(range_v=10.0, digits=s.dc_digits)
    times, volts = [], []
    t0 = time.monotonic()
    for _ in range(s.dc_readings):
        volts.append(dmm.read())
        times.append(time.monotonic() - t0)
    m = Measurement(np.array(times), np.array(volts))

    if abs(m.mean) < PRESENT_V or m.noise_and_drift()[0] > OPEN_NOISE_V:
        return m  # no battery or open leads: ripple would only be interference pickup

    # Fixed range: auto-ranging AC volts takes ~5 s per reading on this DMM.
    progress("Measuring AC ripple…")
    dmm.configure_ac_volts(range_v=RIPPLE_RANGE_V)
    ripple = float(np.mean([dmm.read() for _ in range(s.ripple_readings)]))

    progress("Capturing ripple waveform…")
    dmm.configure_waveform(range_v=10.0, rate_hz=s.wave_rate, points=s.wave_points)
    m.wave = np.array(dmm.read_waveform(s.wave_points))
    m.wave_rate = s.wave_rate
    m.ripple_freq = dominant_frequency(m.wave, s.wave_rate)
    # Over range (NaN) means ripple above 50 mV; take it from the waveform instead.
    m.ripple_rms = ripple if np.isfinite(ripple) else float(np.std(m.wave))

    # The 1 s capture above sets the frequency resolution; this short fast one shows the
    # ripple's shape in the plot.
    progress("Capturing ripple detail…")
    points = int(s.scope_rate * SCOPE_WINDOW_S)
    dmm.configure_waveform(range_v=10.0, rate_hz=s.scope_rate, points=points)
    m.scope = np.array(dmm.read_waveform(points))
    m.scope_rate = s.scope_rate
    return m


def write_csv(path: str, rows: Iterable[tuple[str, Assessment]]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "chemistry", "confidence", "health", "ocv_v", "ripple_mv_rms",
                    "ripple_hz", "soc_pct", "noise_mv", "drift_mv_per_s", "summary", "notes"])
        for stamp, a in rows:
            w.writerow([stamp, a.chemistry, a.confidence, a.health, f"{a.voltage:.5f}",
                        "" if a.ripple_rms is None else f"{a.ripple_rms * 1e3:.4f}",
                        "" if a.ripple_freq is None else f"{a.ripple_freq:.1f}",
                        "" if a.soc_pct is None else f"{a.soc_pct:.0f}",
                        f"{a.noise * 1e3:.4f}", f"{a.drift * 1e3:+.4f}", a.summary,
                        " | ".join(a.notes)])
