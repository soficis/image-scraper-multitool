@echo off
setlocal

title Image Scraper Multitool
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto :missing_venv

".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 goto :broken_venv

for %%a in (%*) do (
    if "%%a"=="--debug" goto :run_console
    if "%%a"=="--console" goto :run_console
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0image_scraper_gui.py" %*
    exit /b 0
)

:run_console
".venv\Scripts\python.exe" "%~dp0image_scraper_gui.py" %*
if errorlevel 1 pause
exit /b %errorlevel%

:missing_venv
echo [ERROR] Virtual environment not found.
echo Please run setup.bat first to set up the environment and install dependencies.
echo.
pause
exit /b 1

:broken_venv
echo [ERROR] The virtual environment appears broken or its base Python was moved/uninstalled.
echo Please run setup.bat to repair and reconfigure the virtual environment.
echo.
pause
exit /b 1
