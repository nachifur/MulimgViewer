@echo off
setlocal
if defined MULIMGVIEWER_PYTHON (
  "%MULIMGVIEWER_PYTHON%" "%~dp0run_tests.py" %*
) else (
  python "%~dp0run_tests.py" %*
)
set "TEST_EXIT=%ERRORLEVEL%"
if "%~1"=="" if not defined CI pause
exit /b %TEST_EXIT%
