@echo off
chcp 65001 >nul
set "ROOT=%~dp0.."
set "TOOL_DIR=%ROOT%\port_manager"
cd /d "%ROOT%"

echo [1/2] 检查 PyInstaller...
python -m pip install "pyinstaller>=6.0.0" -q
if errorlevel 1 (
  echo pip 安装失败，请检查 Python 是否在 PATH 中。
  exit /b 1
)

echo [2/2] 打包单文件 exe...
python -m PyInstaller --noconfirm --onefile --noconsole --specpath "%TOOL_DIR%" --name "端口管理工具" --icon "%TOOL_DIR%\port_icon.ico" --add-data "%TOOL_DIR%\port_icon.ico;." "%TOOL_DIR%\port_manager.py"
if errorlevel 1 exit /b 1

echo.
echo 完成: dist\端口管理工具.exe
echo spec: port_manager\端口管理工具.spec
exit /b 0
