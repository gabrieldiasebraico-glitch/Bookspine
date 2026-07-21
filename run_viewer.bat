@echo off
setlocal
cd /d "%~dp0"
set PORT=8765
if not "%~1"=="" set PORT=%~1

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  start "" "http://127.0.0.1:%PORT%/"
  exit /b 0
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m vocab_mapper.viewer --port %PORT% --open-browser
  goto :eof
)

if exist "INSTALL_WINDOWS.bat" (
  echo Local Python environment was not found. Running setup first...
  call "INSTALL_WINDOWS.bat"
  if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
  ".venv\Scripts\python.exe" -m vocab_mapper.viewer --port %PORT% --open-browser
  goto :eof
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -m vocab_mapper.viewer --port %PORT% --open-browser
  goto :eof
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python -m vocab_mapper.viewer --port %PORT% --open-browser
  goto :eof
)

echo Python 3 was not found. Run INSTALL_WINDOWS.bat first, or install Python 3 and run this file again.
pause
exit /b 1
