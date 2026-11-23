"""Chemistry identification and health assessment for AA rechargeable cells.

Inputs are DMM measurements only (no load is applied), so the assessment is based
on open-circuit voltage, its stability, and the AC ripple on the terminals:

* NiMH ("nickel hydroxide") AA: a bare electrochemical cell, 0.9-1.5 V, with no
  ripple on its terminals.
* Li-ion AA with BMS, 1.5 V type: a 3.7 V Li-ion cell behind a buck regulator and
  protection circuit. Output sits at ~1.5 V regardless of charge, and the switching
  regulator leaves measurable ripple (at no load it runs in burst mode, typically
  tens to hundreds of Hz).
* Li-ion AA with BMS, unregulated (14500): 3.0-4.2 V at the terminals.

Capacity and internal resistance need a load and cannot be measured here.
"""
from dataclasses import dataclass, field

import numpy as np

PRESENT_V = 0.20              # below this, nothing (or no output) is connected. Open leads
                              # wander up to ~±50 mV even at 6.5 digits, so keep a margin.
OPEN_NOISE_V = 0.020          # DC readings wandering more than this: leads open or bad contact

LIION_REG = "Li-ion AA, 1.5 V regulated (BMS)"
LIION_RAW = "Li-ion AA, 3.7 V (14500, BMS)"
NIMH = "NiMH AA (nickel hydroxide)"
UNKNOWN = "Unknown"
NONE = "No battery / no output"
UNSTABLE = "No stable voltage"

GOOD, CHARGE, CHECK, BAD, NO_OUTPUT = "GOOD", "CHARGE", "CHECK", "BAD", "NO OUTPUT"

# Approximate rested open-circuit voltage vs state of charge.
NIMH_SOC = [(1.00, 0), (1.10, 5), (1.20, 15), (1.24, 30), (1.27, 50),
            (1.30, 70), (1.33, 85), (1.36, 95), (1.40, 100)]
LIION_SOC = [(3.00, 0), (3.30, 5), (3.55, 10), (3.65, 20), (3.70, 30), (3.75, 40),
             (3.80, 50), (3.85, 60), (3.92, 70), (4.00, 80), (4.10, 90), (4.20, 100)]


@dataclass(frozen=True)
class Thresholds:
    ripple_switching: float = 0.0005   # V rms; above this a switching regulator is present
    ripple_max: float = 0.020          # V rms; more than this suggests a failing regulator
    max_noise: float = 0.001           # V rms of DC readings after removing drift
    max_drift: float = 0.001           # |V/s|


@dataclass
class Measurement:
    times: np.ndarray                  # DC reading timestamps (s)
    volts: np.ndarray                  # DC readings (V)
    ripple_rms: float | None = None    # AC volts reading (V rms)
    ripple_freq: float | None = None   # dominant ripple frequency (Hz)
    wave: np.ndarray | None = None     # DC-coupled waveform for frequency analysis (V)
    wave_rate: float | None = None     # its sample rate (S/s)
    scope: np.ndarray | None = None    # short high-rate waveform for display (V)
    scope_rate: float | None = None    # its sample rate (S/s)

    @property
    def mean(self) -> float:
        return float(self.volts.mean())

    def noise_and_drift(self) -> tuple[float, float]:
        t, v = self.times, self.volts
        if len(v) >= 3 and t[-1] > t[0]:
            slope, icpt = np.polyfit(t, v, 1)
            return float(np.std(v - (slope * t + icpt), ddof=1)), float(slope)
        return (float(np.std(v, ddof=1)) if len(v) > 1 else 0.0), 0.0


@dataclass
class Assessment:
    chemistry: str
    confidence: str                    # high / medium / low / -
    health: str
    summary: str
    voltage: float
    noise: float
    drift: float
    ripple_rms: float | None
    ripple_freq: float | None
    reversed: bool = False
    soc_pct: float | None = None
    soc_note: str = ""
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _soc(table, v: float) -> float:
    xs, ys = zip(*table)
    return float(np.interp(v, xs, ys))


def dominant_frequency(wave: np.ndarray, rate: float, f_min: float = 5.0) -> float | None:
    if wave is None or len(wave) < 64:
        return None
    ac = wave - wave.mean()
    spec = np.abs(np.fft.rfft(ac * np.hanning(len(ac))))
    freqs = np.fft.rfftfreq(len(ac), 1.0 / rate)
    band = freqs >= f_min
    if not band.any() or spec[band].max() == 0:
        return None
    return float(freqs[band][np.argmax(spec[band])])


def _looks_like_mains(f: float | None) -> bool:
    if not f:
        return False
    return any(abs(f - k * base) <= 2.0 for base in (50.0, 60.0) for k in range(1, 6))


def assess(m: Measurement, th: Thresholds = Thresholds()) -> Assessment:
    v = m.mean
    av = abs(v)
    noise, drift = m.noise_and_drift()
    rip = m.ripple_rms
    in_regulation = 1.45 <= av <= 1.60
    mains = _looks_like_mains(m.ripple_freq)
    # Ripple at a mains frequency is more likely lead pickup than a regulator, unless the
    # voltage also sits in the 1.5 V regulation window.
    switching = (rip is not None and rip >= th.ripple_switching
                 and (not mains or in_regulation))
    a = Assessment(UNKNOWN, "low", CHECK, "", v, noise, drift, rip, m.ripple_freq,
                   reversed=v <= -PRESENT_V)

    def ev(s):
        a.evidence.append(s)

    if noise > OPEN_NOISE_V:
        a.chemistry, a.confidence, a.health = UNSTABLE, "-", CHECK
        a.reversed = False
        a.summary = ("The reading is wandering, as it does when the test leads are open or a "
                     "contact is intermittent. Check the battery connection and retest.")
        ev(f"DC readings spread {np.ptp(m.volts) * 1e3:.0f} mV ({noise * 1e3:.1f} mV rms)")
        return a

    if av < PRESENT_V:
        a.chemistry, a.confidence, a.health = NONE, "-", NO_OUTPUT
        a.summary = ("No voltage. Either no battery is connected, a Li-ion AA's BMS has switched "
                     "its output off (fully discharged or protection tripped), or the cell is dead. "
                     "Recharge and retest; if it still reads 0 V, the cell has failed.")
        ev(f"|OCV| {av * 1e3:.1f} mV < {PRESENT_V * 1e3:.0f} mV")
        return a

    if a.reversed:
        a.notes.append("Battery is reversed (negative voltage). Flip it; chemistry is judged on |V|.")
    ev(f"OCV {av:.4f} V")
    if rip is not None:
        f_txt = f" at {m.ripple_freq:.0f} Hz" if m.ripple_freq else ""
        if switching:
            kind = "switching regulator present"
        elif rip >= th.ripple_switching:
            kind = "at a mains frequency: treated as lead pickup, not a regulator"
        else:
            kind = "no regulator ripple"
        ev(f"Ripple {rip * 1e3:.3f} mV rms{f_txt} ({kind})")
        if switching and mains:
            a.notes.append("Ripple frequency is near a mains harmonic; it may be pickup on the test "
                           "leads rather than a regulator. Check wiring if the type looks wrong.")

    if 2.5 <= av <= 4.5:
        a.chemistry, a.confidence = LIION_RAW, "high"
        ev("Voltage above 2.5 V: only a Li-ion cell can produce this")
        a.soc_pct = _soc(LIION_SOC, av)
        a.soc_note = "Estimated from rested Li-ion OCV (±10%)."
        if av > 4.25:
            a.health, a.summary = BAD, "Overcharged: above 4.25 V. Stop charging; the charger or BMS may be faulty."
        elif av < 3.0:
            a.health, a.summary = BAD, ("Over-discharged below 3.0 V; the BMS should have cut off. "
                                        "Do not recharge; replace the cell.")
        elif av < 3.5:
            a.health, a.summary = CHARGE, "Nearly empty. Recharge before use."
        else:
            a.health, a.summary = GOOD, "Cell voltage healthy."
    elif switching and 1.0 <= av <= 1.7:
        a.chemistry, a.confidence = LIION_REG, "medium" if mains else "high"
        ev("~1.5 V output with switching ripple: built-in regulator (NiMH has no electronics)")
        a.soc_note = ("Not measurable: the regulator holds the output at ~1.5 V until the BMS "
                      "cuts off, so voltage does not track charge.")
        if 1.45 <= av <= 1.60:
            a.health, a.summary = GOOD, "Regulated output within 1.45-1.60 V."
        elif av < 1.45:
            a.health, a.summary = CHARGE, ("Output sagging below regulation: the internal cell is "
                                           "nearly empty. Recharge; replace if it stays low after a full charge.")
        else:
            a.health, a.summary = BAD, "Output above 1.60 V: regulator fault."
        if rip > th.ripple_max:
            a.health = BAD if a.health == BAD else CHECK
            a.notes.append(f"Ripple above {th.ripple_max * 1e3:.0f} mV rms: the regulator may be failing.")
    elif 1.7 < av < 2.5:
        a.chemistry, a.confidence, a.health = UNKNOWN, "low", BAD
        a.summary = ("Voltage fits neither chemistry. Possibly an over-discharged unregulated Li-ion "
                     "cell. Do not recharge.")
    elif av > 1.50 and not switching:
        a.chemistry, a.confidence, a.health = UNKNOWN, "low", CHECK
        a.summary = ("Above the NiMH range but no regulator ripple. Possibly a NiMH straight off the "
                     "charger (retest after an hour's rest), a 1.5 V Li-ion with a linear regulator, "
                     "or a non-rechargeable alkaline/lithium cell.")
        if drift < -th.max_drift / 4:
            a.notes.append("Voltage is falling, consistent with a freshly charged NiMH settling.")
    elif av > 4.5:
        a.chemistry, a.confidence, a.health = UNKNOWN, "low", BAD
        a.summary = "Voltage above any AA cell. Check what is connected."
    else:  # 0.05-1.50 V, no switching ripple
        a.chemistry = NIMH
        a.confidence = "high" if 1.0 <= av <= 1.45 else "medium"
        ev("Below 1.5 V with no regulator ripple: bare electrochemical cell")
        a.soc_pct = _soc(NIMH_SOC, av)
        a.soc_note = "Rough estimate: NiMH OCV is flat, so ±20%. Most accurate after a few hours' rest."
        if av >= 1.40:
            a.health, a.summary = GOOD, "Fully charged."
            a.notes.append("Above 1.40 V usually means surface charge from recent charging; "
                           "it settles to about 1.35 V.")
        elif av >= 1.25:
            a.health, a.summary = GOOD, "Charge level healthy."
        elif av >= 0.90:
            a.health, a.summary = CHARGE, "Low. Recharge before use."
        else:
            a.health, a.summary = BAD, ("Deeply discharged below 0.9 V and may be damaged. Slow-charge "
                                        "and retest; replace if it won't hold a charge.")
        if rip is None:
            a.confidence = "medium"
            a.notes.append("Ripple was not measured, so a 1.5 V Li-ion could not be ruled out.")

    # Stability (applies to every chemistry)
    if noise > th.max_noise:
        a.notes.append(f"Unstable reading: {noise * 1e3:.2f} mV rms noise. Check the contacts.")
        if a.health == GOOD:
            a.health = CHECK
    if abs(drift) > th.max_drift:
        settling = a.chemistry == NIMH and drift < 0 and av >= 1.38
        if settling:
            a.notes.append(f"Falling {drift * 1e3:+.2f} mV/s: surface charge settling after charging.")
        else:
            a.notes.append(f"Voltage drifting {drift * 1e3:+.2f} mV/s. Check contacts; "
                           "a steady fall can mean an internal short.")
            if a.health == GOOD:
                a.health = CHECK
    if a.reversed and a.health == GOOD:
        a.health = CHECK
    return a
