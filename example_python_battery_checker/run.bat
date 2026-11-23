@echo off
rem Starts the battery checker. Extra arguments are passed through, e.g.
rem   run.bat --dmm PXI1Slot4
rem   run.bat --once
setlocal
set "HERE=%~dp0"
if not exist "%HERE%.venv\Scripts\python.exe" (
    echo The virtual environment is missing. Run setup.bat first.
    pause
    exit /b 1
)

rem The package is this folder, so run from its parent so that this copy (and not
rem one elsewhere) is what "python -m <folder name>" imports. The package name is
rem taken from the folder name, so the folder can be renamed (letters, digits, _ only).
for %%I in ("%HERE%..") do set "ROOT=%%~fI"
for %%I in ("%HERE%.") do set "PKG=%%~nxI"
set "PYTHONPATH=%ROOT%"
cd /d "%ROOT%"

"%HERE%.venv\Scripts\python.exe" -m %PKG% %*
if errorlevel 1 pause
