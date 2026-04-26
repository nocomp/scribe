@echo off
chcp 65001 > nul 2>&1
cd /d "%~dp0"

echo.
echo  =====================================================
echo   SCRIBE - Mode Exercice Multi-Sites
echo  =====================================================
echo.
echo  Lance 6 instances SCRIBE fictives + 1 collecteur animateur :
echo    Animateur     : http://localhost:8565
echo    CH_NORD       : http://localhost:8660
echo    CH_SUD        : http://localhost:8661
echo    CHU_CENTRE    : http://localhost:8662
echo    CH_EST        : http://localhost:8663
echo    CH_OUEST      : http://localhost:8664
echo    CLINIQUE_DEMO : http://localhost:8665
echo.

python --version > nul 2>&1
if errorlevel 1 ( echo [ERREUR] Python introuvable & pause & exit /b 1 )

REM ── Collecteur animateur (port 8565)
echo  [1/7] Demarrage collecteur animateur (port 8565)...
start "SCRIBE Collecteur" cmd /k "set SCRIBE_EXERCICE_MODE=1 && set COLLECTEUR_PORT=8565 && cd collecteur_exercice && python collecteur_exercice.py"
timeout /t 5 /nobreak > nul

REM ── Sites fictifs
call :LAUNCH "CH_NORD"        "config_exo_ch_nord.xml"        "scribe_exo_ch_nord.db"        "8660"
call :LAUNCH "CH_SUD"         "config_exo_ch_sud.xml"         "scribe_exo_ch_sud.db"         "8661"
call :LAUNCH "CHU_CENTRE"     "config_exo_chu_centre.xml"     "scribe_exo_chu_centre.db"     "8662"
call :LAUNCH "CH_EST"         "config_exo_ch_est.xml"         "scribe_exo_ch_est.db"         "8663"
call :LAUNCH "CH_OUEST"       "config_exo_ch_ouest.xml"       "scribe_exo_ch_ouest.db"       "8664"
call :LAUNCH "CLINIQUE_DEMO"  "config_exo_clinique_demo.xml"  "scribe_exo_clinique_demo.db"  "8665"

echo.
echo  =====================================================
echo   EXERCICE EN COURS
echo  =====================================================
echo   Animateur        : http://localhost:8565
echo                       Login : animateur / Animateur2026!
echo   Sites joueurs    : http://localhost:8660 a 8665
echo                       Login : dircrise / Exercice2026!
echo   Vue mobile       : http://localhost:8660/m
echo  =====================================================
echo.
echo  Pour arreter, fermez les fenetres de console ouvertes.
pause
exit /b 0

:LAUNCH
set SIGLE=%~1
set CFG=%~2
set DB=%~3
set PORT=%~4
echo  [%PORT%] Demarrage %SIGLE%...
start "SCRIBE %SIGLE% (:%PORT%)" cmd /k "set DATABASE_URL=sqlite:///%CD%\%DB% && set SCRIBE_PORT=%PORT% && set SCRIBE_CONFIG_FILE=%CD%\%CFG% && set SCRIBE_EXERCICE_MODE=1 && set SCRIBE_EXO_SIGLE=%SIGLE% && set SCRIBE_EXO_COLLECTEUR=http://localhost:8565 && set SCRIBE_ADMIN_USER=dircrise && set SCRIBE_ADMIN_PASS=Exercice2026! && (if not exist %DB% python setup.py) && python main.py"
timeout /t 3 /nobreak > nul
goto :eof
