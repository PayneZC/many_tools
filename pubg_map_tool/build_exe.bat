@echo off
chcp 65001 >nul
set "ROOT=%~dp0.."
set "TOOL_DIR=%ROOT%\pubg_map_tool"
cd /d "%ROOT%"

REM 优先使用 Miniconda 环境（与启动.bat 一致）
set "PYTHON=python"
if exist "%USERPROFILE%\miniconda3\envs\ai_train\python.exe" (
  set "PYTHON=%USERPROFILE%\miniconda3\envs\ai_train\python.exe"
) else if exist "%USERPROFILE%\miniconda3\python.exe" (
  set "PYTHON=%USERPROFILE%\miniconda3\python.exe"
)

echo [1/3] 检查依赖...
"%PYTHON%" -m pip install "pyinstaller>=6.0.0" "pillow>=10.0.0" "pillow-avif-plugin>=1.4.0" -q
if errorlevel 1 (
  echo pip 安装失败，请检查 Python 环境。
  exit /b 1
)

taskkill /F /IM "PUBG地图工具.exe" >nul 2>&1
taskkill /F /IM "PUBGMapTool_build.exe" >nul 2>&1
REM 避免 timeout 在重定向 stdin 时报错
ping 127.0.0.1 -n 2 >nul

echo [2/3] 生成图标并打包...
"%PYTHON%" "%TOOL_DIR%\generate_icons.py"
if errorlevel 1 exit /b 1

"%PYTHON%" "%TOOL_DIR%\finalize_build.py" clean
if errorlevel 1 exit /b 1

"%PYTHON%" -m PyInstaller --noconfirm --clean "%TOOL_DIR%\pubg_map_tool.spec"
if errorlevel 1 exit /b 1

echo [3/3] 重命名并启动冒烟测试...
"%PYTHON%" "%TOOL_DIR%\finalize_build.py" finalize
if errorlevel 1 exit /b 1

echo.
echo 完成: dist\PUBG地图工具.exe
echo spec: pubg_map_tool\pubg_map_tool.spec
exit /b 0
