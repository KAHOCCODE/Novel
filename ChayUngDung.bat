@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Novel Downloader Pro

if not exist ".venv\Scripts\python.exe" (
    echo Chua tim thay moi truong cua ung dung.
    echo Hay chay CaiDat.bat truoc.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo Ung dung da dung do gap loi.
    echo Hay chup lai toan bo noi dung cua so nay de kiem tra.
    echo.
    pause
    exit /b 1
)

exit /b 0
