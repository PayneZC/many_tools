@echo off
chcp 65001 >nul
set "TOOL_DIR=%~dp0"
set "ROOT=%TOOL_DIR%.."
cd /d "%ROOT%"

rem 调用 build_exe.ps1（自动选用 Miniconda Python + Conda 运行库）
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); & '%TOOL_DIR%build_exe.ps1'"
if errorlevel 1 (
  echo 打包失败。
  pause
  exit /b 1
)

pause
exit /b 0
