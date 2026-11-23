"""AA battery health checker.

    python -m example_python_battery_checker          open the GUI
    python -m example_python_battery_checker --once   test the connected battery and print the result
"""
import argparse
import sys

from .dmm import Dmm

from .analysis import assess
from .measure import run_test


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="example_python_battery_checker", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run one test in the console, no GUI")
    ap.add_argument("--dmm", default="PXI1Slot3", help="DMM resource name (default: PXI1Slot3)")
    args = ap.parse_args(argv)

    if not args.once:
        from .gui import BatteryGui
        BatteryGui(args.dmm).mainloop()
        return 0

    with Dmm(args.dmm) as dmm:
        m = run_test(dmm, progress=lambda msg: print(msg))
    a = assess(m)
    print(f"\nType:    {a.chemistry} ({a.confidence} confidence)")
    print(f"Health:  {a.health} - {a.summary}")
    print(f"OCV:     {a.voltage:+.5f} V   noise {a.noise * 1e3:.3f} mV   drift {a.drift * 1e3:+.4f} mV/s")
    if a.ripple_rms is not None:
        print(f"Ripple:  {a.ripple_rms * 1e3:.3f} mV rms" +
              (f" at {a.ripple_freq:.1f} Hz" if a.ripple_freq else ""))
    print(f"Charge:  {'n/a' if a.soc_pct is None else f'{a.soc_pct:.0f}%'} - {a.soc_note}")
    for e in a.evidence:
        print(f"  * {e}")
    for n in a.notes:
        print(f"  ! {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
