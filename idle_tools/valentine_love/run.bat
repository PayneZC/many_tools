@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "HTML=%~dp0index.html"
set "URL=file:///%HTML:\=/%"

REM 优先 Edge 应用模式（无边栏，更像桌面程序）
where msedge >nul 2>&1
if %errorlevel% equ 0 (
  start "" msedge --new-window --app="%URL%" --window-size=1280,800
  exit /b 0
)

REM 其次 Chrome 应用模式
where chrome >nul 2>&1
if %errorlevel% equ 0 (
  start "" chrome --new-window --app="%URL%" --window-size=1280,800
  exit /b 0
)

REM 回退：系统默认浏览器打开
start "" "%HTML%"
exit /b 0
