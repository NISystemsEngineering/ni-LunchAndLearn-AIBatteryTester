@echo off
rem One-time setup: creates .venv in this folder and installs the Python packages.
setlocal
cd /d "%~dp0"

rem --- Find Python 3.10+ (prefer the py launcher) ---
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo ERROR: Python 3.10 or newer was not found.
    echo Install it from https://www.python.org/downloads/windows/ and tick
    echo "tcl/tk and IDLE" and "Add python.exe to PATH" in the installer, then run setup.bat again.
    goto :fail
)
echo Using: & %PY% --version

%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo ERROR: This Python has no tkinter. Re-run the Python installer, choose Modify,
    echo and tick "tcl/tk and IDLE".
    goto :fail
)

rem --- Create the virtual environment ---
if exist ".venv\Scripts\python.exe" (
    echo .venv already exists - updating packages.
) else (
    echo Creating virtual environment in %~dp0.venv ...
    %PY% -m venv .venv || goto :fail
)

".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail

rem --- NI-DMM driver can't be installed by pip; just check for it ---
if not exist "C:\Program Files\IVI Foundation\IVI\Bin\nidmm_64.dll" (
    echo.
    echo WARNING: NI-DMM driver not found ^(nidmm_64.dll^).
    echo Install NI-DMM from https://www.ni.com/en/support/downloads/drivers/download.ni-dmm.html
    echo before running the app.
)

echo.
echo Setup complete. Start the app with run.bat
pause
exit /b 0

:fail
echo.
echo Setup failed.
pause
exit /b 1
