# AA Battery Checker (Python)

Identifies the chemistry of an AA rechargeable cell (NiMH, 1.5 V regulated Li-ion with a
battery management system (BMS), or 3.7 V 14500 Li-ion), estimates its health and state of
charge, and flags bad cells. It uses only an NI PXIe-4082 DMM. No load is applied to the
battery, so capacity and internal resistance are not measured.

## What you need

| Requirement | Notes |
|---|---|
| Windows, 64-bit | |
| **NI-DMM driver** | Install from [ni.com](https://www.ni.com/en/support/downloads/drivers/download.ni-dmm.html). The app loads `C:\Program Files\IVI Foundation\IVI\Bin\nidmm_64.dll` directly. |
| **Python 3.10 or newer** | From [python.org](https://www.python.org/downloads/windows/). In the installer, keep **tcl/tk and IDLE** ticked (the GUI uses tkinter). |
| A DMM visible in NI MAX | The default resource name is `PXI1Slot3`. |

The Python packages (numpy, matplotlib) are installed for you by `setup.bat`.

## First-time setup

1. Copy this whole `example_python_battery_checker` folder anywhere you like.
2. Double-click **`setup.bat`**. It creates a private Python environment in `.venv`
   inside this folder and installs the packages. It does not change your system
   Python. It also warns you if the NI-DMM driver is missing.

You only need to do this once. To repair or update the packages, run `setup.bat` again.
To start over, delete the `.venv` folder and run `setup.bat`.

## Running

Double-click **`run.bat`** to open the GUI.

From a command prompt you can pass options:

```
run.bat --dmm PXI1Slot4     use a different DMM resource name
run.bat --once              test the connected battery once and print the result (no GUI)
run.bat --help
```

## Files

| File | Purpose |
|---|---|
| `__main__.py` | Command-line entry point (GUI or `--once`) |
| `gui.py` | tkinter/matplotlib user interface |
| `worker.py` | Background thread that talks to the DMM |
| `measure.py` | DMM measurement sequence and CSV export |
| `analysis.py` | Chemistry identification and health assessment |
| `dmm.py` | Small ctypes wrapper around the NI-DMM C driver |
| `requirements.txt`, `setup.bat`, `run.bat` | Environment setup and launcher |

Don't copy the `.venv` folder to another PC. It only works on the machine where it was
created, so run `setup.bat` on each PC instead.

## Troubleshooting

- **"NI-DMM driver not found"**: install NI-DMM (see above).
- **"Python 3.10 or newer was not found"**: install Python, or tick *Add python.exe to PATH*.
- **"This Python has no tkinter"**: re-run the Python installer, choose *Modify*, and tick *tcl/tk and IDLE*.
- **NI-DMM error on startup**: check the resource name in NI MAX and pass it with `--dmm`.
