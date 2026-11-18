@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "%~dp0선석조회.py"
echo.
echo 확인판(모선_일정_변경_확인판.html)을 새로고침하면 반영됩니다.
pause
