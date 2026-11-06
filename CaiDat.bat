@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Novel Downloader - Cai dat
echo ===============================================
echo       NOVEL DOWNLOADER PRO - CAI DAT
echo ===============================================
echo.

set "PYTHON_EXE="
for /f "usebackq delims=" %%P in (`python.exe -c "import sys; print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
    for /f "usebackq delims=" %%P in (`py.exe -3 -c "import sys; print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if not defined PYTHON_EXE (
    echo [LOI] Khong tim thay Python 3 tren may.
    echo Hay cai Python 3.10 tro len va chon Add Python to PATH.
    echo.
    pause
    exit /b 1
)

echo [1/4] Python duoc tim thay:
echo       %PYTHON_EXE%
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Dang tao moi truong rieng cho ung dung...
    "%PYTHON_EXE%" -m venv ".venv"
    if errorlevel 1 goto :venv_error
) else (
    echo [2/4] Moi truong rieng da ton tai.
)

echo [3/4] Dang cap nhat pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :install_error

echo [4/4] Dang cai thu vien can thiet...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 goto :install_error

echo.
echo ===============================================
echo CAI DAT HOAN TAT
echo Hay mo file ChayUngDung.bat de su dung.
echo ===============================================
echo.
pause
exit /b 0

:venv_error
echo.
echo [LOI] Khong tao duoc moi truong Python rieng.
echo Thu cai lai Python va danh dau tuy chon Add Python to PATH.
echo.
pause
exit /b 1

:install_error
echo.
echo [LOI] Cai thu vien chua hoan tat.
echo Kiem tra ket noi mang, sau do chay lai CaiDat.bat.
echo.
pause
exit /b 1
