@echo off
setlocal

title Image Scraper Multitool - One-Click Setup
cd /d "%~dp0"

echo ======================================================
echo       Image Scraper Multitool - Automated Setup
echo ======================================================
echo.

REM 1. Detect Python executable
set "PYTHON_CMD="

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if %errorlevel% equ 0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD goto :no_python

REM 2. Check Python version (>= 3.8)
echo [*] Checking Python installation...
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if errorlevel 1 goto :bad_python_version

echo [+] Found compatible Python:
%PYTHON_CMD% --version

REM 3. Check/Setup virtual environment
if not exist ".venv\Scripts\python.exe" goto :make_venv

".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 goto :repair_venv

echo [+] Existing virtual environment found.
goto :install_deps

:repair_venv
echo [*] Existing virtual environment is broken. Recreating .venv...
rmdir /s /q .venv >nul 2>&1

:make_venv
echo [*] Creating virtual environment (.venv)...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 goto :venv_fail
echo [+] Virtual environment created successfully.

:install_deps
REM 4. Upgrade pip and install production dependencies
echo [*] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo [*] Installing dependencies from requirements.txt...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_fail
echo [+] Dependencies installed successfully.

REM 5. Optional developer tools
echo.
set "INSTALL_DEV="
set /p INSTALL_DEV="Would you like to install developer/test tools (pytest, ruff, mypy)? [y/N]: "
if /i "%INSTALL_DEV%"=="y" (
    echo [*] Installing dev dependencies from requirements-dev.txt...
    ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
    if not errorlevel 1 (
        echo [+] Developer dependencies installed.
    ) else (
        echo [!] Warning: Dev dependencies could not be fully installed.
    )
)

echo.
echo ======================================================
echo                  Setup Completed!
echo ======================================================
echo You can run the application anytime by double-clicking run.bat
echo.

REM 6. Launch prompt
set "LAUNCH_NOW="
set /p LAUNCH_NOW="Would you like to launch the GUI now? [Y/n]: "
if /i "%LAUNCH_NOW%"=="n" goto :finish

echo [*] Launching Image Scraper Multitool...
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" image_scraper_gui.py
) else (
    start "" ".venv\Scripts\python.exe" image_scraper_gui.py
)

:finish
exit /b 0

:no_python
echo [ERROR] Python was not found on your system.
echo Please install Python 3.8 or higher from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:bad_python_version
echo [ERROR] Python 3.8 or higher is required.
echo Detected version:
%PYTHON_CMD% --version
echo Please install a compatible Python version.
echo.
pause
exit /b 1

:venv_fail
echo [ERROR] Failed to create virtual environment.
echo Please ensure python-venv or ensurepip is available.
echo.
pause
exit /b 1

:pip_fail
echo [ERROR] Failed to install dependencies from requirements.txt.
echo.
pause
exit /b 1
