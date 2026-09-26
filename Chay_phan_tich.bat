@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Dang cap nhat du lieu va phan tich...
python run.py --serve
pause
