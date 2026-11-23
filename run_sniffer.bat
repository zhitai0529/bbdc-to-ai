@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
call ".venv\Scripts\activate.bat"
python -m src.launcher --mumu
if errorlevel 1 pause
exit /b
:missing
echo 请先双击 setup.bat 安装虚拟环境和依赖。
pause
exit /b 1
