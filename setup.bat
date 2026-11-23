@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist config.yaml copy /Y config.example.yaml config.yaml >nul
if not exist config.yaml goto failed
if exist ".venv\Scripts\python.exe" goto install
python --version >nul 2>&1
if errorlevel 1 goto no_python
python -m venv .venv
if errorlevel 1 goto failed
:install
call ".venv\Scripts\activate.bat"
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo 安装完成。双击 run_sniffer.bat 启动。
pause
exit /b 0
:no_python
echo 未找到 Python。请安装 Python 3.10 或更高版本，并加入 PATH。
:failed
echo 安装失败，请根据上方错误检查 Python 版本或网络。
pause
exit /b 1
