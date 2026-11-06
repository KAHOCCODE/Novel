@echo off
cd /d "%~dp0"
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.browsers"
set "TEMP=%~dp0.nd-data\runtime"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist ".venv\Scripts\python.exe" (
 echo Hay chay CaiDat.bat truoc.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-browser.txt
if errorlevel 1 (
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
 echo Cai trinh duyet chua thanh cong.
 pause
 exit /b 1
)
echo Da cai Chromium. Chi duoc chay khi ban chon che do trinh duyet.
pause
