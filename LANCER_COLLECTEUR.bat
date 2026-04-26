@echo off
chcp 65001 >nul
title SCRIBE Collecteur (port 9000)
cd /d "%~dp0\collecteur"
echo.
echo  SCRIBE Collecteur territorial v1.4.0
echo  Port 9000
echo.
pip install -r collecteur_requirements.txt -q
echo  Dashboard : http://localhost:9000
echo.
python3.8 collecteur.py 2>nul || python3 collecteur.py 2>nul || python collecteur.py
pause
