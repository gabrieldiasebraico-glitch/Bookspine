@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$shell = New-Object -ComObject WScript.Shell; $desktop = [Environment]::GetFolderPath('Desktop'); $shortcut = $shell.CreateShortcut((Join-Path $desktop 'Bookspine Vocabulary Maps.lnk')); $shortcut.TargetPath = (Join-Path (Get-Location) 'run_viewer.bat'); $shortcut.WorkingDirectory = (Get-Location).Path; $shortcut.IconLocation = (Join-Path (Get-Location) 'vocab_mapper\web_viewer\assets\bookspine-logo.ico'); $shortcut.Save()"

if %ERRORLEVEL% NEQ 0 (
  echo Could not create the desktop shortcut.
  pause
  exit /b %ERRORLEVEL%
)

echo Desktop shortcut created.
pause
