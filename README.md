# AI Battery Health and Chemistry Tester

A demo of using Claude to build NI test software for real hardware and a real DUT: an AA
battery checker that identifies chemistry (Alkaline, Ni-MH or 1.5 V Li-ion with a BMS),
estimates charge and flags bad cells, using only an NI PXIe-4082 DMM. The same task was
built twice, once in LabVIEW and once in Python.

## Folder structure

```
AI Battery Test Demo.pptx            Slide deck walking through the demo
example_labview_battery_checker/     LabVIEW version (built with the LabVIEW MCP plugin)
  Battery Health Checker.lvproj      Project file; open this first
  Battery Health Checker.vi          Top-level UI: auto-detects a battery and runs the test
  Hardware/                          DMM measurement VIs (voltage, ripple, internal resistance)
  Analysis/                          Chemistry classification and charge estimate
  spec.txt                           Measurement method, thresholds and calibration data
  build-contract.json                VI interfaces used to drive the Claude build agents
example_python_battery_checker/      Python version (tkinter + matplotlib GUI)
  setup.bat / run.bat                One-time setup and launcher
  README.md                          Detailed setup, usage and troubleshooting
```

## Hardware

- NI PXIe-4082 DMM, resource name `PXI1Slot3` by default (check in NI MAX)
- An AA battery holder wired directly to the DMM's HI / LO (V-Ohm) inputs. No load or other hardware.

## Dependencies

| | LabVIEW version | Python version |
|---|---|---|
| OS | Windows 64-bit | Windows 64-bit |
| Runtime | LabVIEW 2026 | Python 3.10+ with tkinter |
| NI driver | NI-DMM (LabVIEW API) | NI-DMM (`nidmm_64.dll`, loaded via ctypes) |
| Packages | none | numpy, matplotlib (installed by `setup.bat`) |
| To build/modify with Claude | Claude Code + LabVIEW MCP plugin (`labview-mcp`) | Claude Code |

## Quick start

- **LabVIEW:** open `Battery Health Checker.lvproj`, run `Battery Health Checker.vi`, insert a battery.
- **Python:** run `setup.bat` once, then `run.bat`. See `example_python_battery_checker/README.md`.
