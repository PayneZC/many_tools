@echo off
chcp 65001 >nul
set "ROOT=%~dp0.."
set "TOOL_DIR=%ROOT%\recoil_macro"
cd /d "%ROOT%"

rem 使用 UTF-8 调用 PowerShell，避免中文参数乱码
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); & '%TOOL_DIR%\build_exe.ps1'"
if errorlevel 1 (
  echo 打包失败。
  pause
  exit /b 1
)

pause
exit /b 0
