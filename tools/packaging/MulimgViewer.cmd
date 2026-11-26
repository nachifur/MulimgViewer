@echo off
setlocal
cd /d "%~dp0"
set "PYTHONNOUSERSITE=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "PATH=%CD%;%CD%\Library\bin;%CD%\Scripts;%PATH%"
if not exist ".relocated" (
    "python.exe" "Scripts\conda-unpack-script.py" || exit /b 1
    type nul > ".relocated" || exit /b 1
)
cd viewer
if "%~1"=="--self-check" (
    "..\python.exe" self_check.py
) else (
    "..\pythonw.exe" MulimgViewer.py %*
)
exit /b %errorlevel%
