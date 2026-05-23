@echo off
chcp 65001 > nul 2>&1
cd /d "%~dp0"
title SCRIBE - Supervision + Pilotage d'instances

REM v2.4.8.4 — Support de l'option --reset pour repartir d'un état propre
REM (nettoie les flags onboarding + supprime les DB d'instances + state master)
if /i "%1"=="--reset" goto :do_reset
if /i "%1"=="-r"      goto :do_reset
if /i "%1"=="/reset"  goto :do_reset
goto :no_reset

:do_reset
echo.
echo  ============================================================
echo   SCRIBE - RESET COMPLET
echo  ============================================================
echo.
echo   Va supprimer :
echo     - master\.onboarding_done    (flag onboarding)
echo     - master\.wizard_force       (flag wizard)
echo     - master\master_instances*.json (state des instances)
echo     - data\instances\*           (toutes les DBs d'instances)
echo     - logs\*                     (anciens logs)
echo.
echo   Les comptes de supervision et les configs racine sont preserves.
echo.
set /p CONFIRM=Confirmer le reset (oui/N) ?
if /i not "%CONFIRM%"=="oui" (
    echo.
    echo  Annule. SCRIBE n'a pas ete lance.
    pause
    exit /b 0
)
echo.
echo  [reset] Suppression des flags onboarding...
if exist master\.onboarding_done del /f /q master\.onboarding_done
if exist master\.wizard_force    del /f /q master\.wizard_force
echo  [reset] Suppression du state des instances...
if exist master\master_instances.json           del /f /q master\master_instances.json
if exist master\master_instances_exercice.json  del /f /q master\master_instances_exercice.json
echo  [reset] Suppression des DBs d'instances...
if exist data\instances           rmdir /s /q data\instances 2>nul
if exist data\instances_exercice  rmdir /s /q data\instances_exercice 2>nul
echo  [reset] Nettoyage des logs...
if exist logs\*.log del /f /q logs\*.log 2>nul
echo  [reset] OK. SCRIBE va se relancer dans un etat propre.
echo.
goto :continue

:no_reset
echo.
echo  ===============================================================
echo   SCRIBE - Supervision avec pilotage d'instances
echo.
echo   http://localhost:9000  -- Onglet "INSTANCES"
echo.
echo   Lancez/configurez vos instances depuis l'admin web.
echo   Ctrl+C pour arreter (toutes les instances filles aussi).
echo.
echo   Astuce : LANCER_SCRIBE.bat --reset pour repartir a zero.
echo  ===============================================================
echo.

:continue
REM Detection Python
where python >nul 2>&1
if errorlevel 1 (
    echo  X Python non trouve. Installez Python 3.10+.
    pause
    exit /b 1
)

REM Dependances
echo  [info] Verification des dependances...
if exist requirements.txt python -m pip install -q -r requirements.txt 2>nul
if exist collecteur\collecteur_requirements.txt python -m pip install -q -r collecteur\collecteur_requirements.txt 2>nul

REM Repertoires
if not exist data\instances mkdir data\instances
if not exist logs mkdir logs

REM Profil de base
if not exist master\profil_base.xlsx (
    if exist SCRIBE_config_etablissement.xlsx (
        echo  [setup] Copie du profil de base...
        copy /Y SCRIBE_config_etablissement.xlsx master\profil_base.xlsx >nul
    )
)

echo.
echo  ^>^> Demarrage de la supervision sur :9000...
echo.

cd collecteur
python collecteur.py
pause
