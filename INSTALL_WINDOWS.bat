@echo off
setlocal
cd /d "%~dp0"

set PYTHON_INSTALLER=installers\python-3.12.10-amd64.exe
set WHEELHOUSE=installers\wheelhouse
set PY_CMD=

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
  if %ERRORLEVEL% EQU 0 set PY_CMD=py -3.12
)

if not defined PY_CMD (
  where python >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
    if %ERRORLEVEL% EQU 0 set PY_CMD=python
  )
)

if not defined PY_CMD (
  if not exist "%PYTHON_INSTALLER%" (
    echo Python 3.12 was not found, and %PYTHON_INSTALLER% is missing.
    pause
    exit /b 1
  )
  echo Installing Python 3.12 for the current user...
  start /wait "" "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 InstallLauncherAllUsers=0 Include_pip=1 Include_test=0
  if %ERRORLEVEL% NEQ 0 (
    echo Python 3.12 installer failed with exit code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
  )
  where py >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
    if %ERRORLEVEL% EQU 0 set PY_CMD=py -3.12
  )
  if not defined PY_CMD (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
  )
)

if not defined PY_CMD (
  echo Python 3.12 installation did not become available on PATH. Open a new Command Prompt and run this file again.
  pause
  exit /b 1
)

if not exist "%WHEELHOUSE%" (
  echo Offline wheelhouse was not found at %WHEELHOUSE%.
  pause
  exit /b 1
)

echo Creating local virtual environment...
%PY_CMD% -m venv .venv
if %ERRORLEVEL% NEQ 0 (
  echo Could not create the local virtual environment.
  pause
  exit /b %ERRORLEVEL%
)

echo Installing bundled Python dependencies...
".venv\Scripts\python.exe" -m pip install --no-index --find-links "%WHEELHOUSE%" -r requirements-viewer.txt
if %ERRORLEVEL% NEQ 0 (
  echo Dependency installation failed.
  pause
  exit /b %ERRORLEVEL%
)

echo Setup complete. Run run_viewer.bat to start Bookspine Vocabulary Maps.
pause
