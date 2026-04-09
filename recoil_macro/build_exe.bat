@echo off
chcp 65001 >nul
set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo [1/2] 检查 PyInstaller...
python -m pip install "pyinstaller>=6.0.0" -q
if errorlevel 1 (
  echo pip 安装失败，请检查 Python 是否在 PATH 中。
  exit /b 1
)

echo [2/2] 打包单文件 exe...
python -m PyInstaller --noconfirm recoil_macro\recoil_macro.spec
if errorlevel 1 exit /b 1

echo.
echo 完成: dist\recoil_macro.exe
exit /b 0
