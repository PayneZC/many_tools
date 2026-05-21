@echo off
chcp 65001 >nul
set "TOOL_DIR=%~dp0"
set "ROOT=%TOOL_DIR%..\..\"
cd /d "%ROOT%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); & '%TOOL_DIR%build_exe.ps1'"
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

pause
exit /b 0
