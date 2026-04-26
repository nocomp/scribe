@echo off
chcp 65001 > nul 2>&1
cd /d "%~dp0"

echo.
echo  =====================================================
echo   SCRIBE - Configuration et demarrage
echo   github.com/nocomp/scribe
echo  =====================================================
echo.

python --version > nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Python introuvable.
    echo  Installez Python 3.9 ou superieur depuis python.org
    pause
    exit /b 1
)

if not exist requirements.txt (
    echo  [ERREUR] requirements.txt introuvable.
    pause
    exit /b 1
)

echo  Installation des dependances Python...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERREUR] Echec installation. Essayez :
    echo    python -m pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist config.xml (
    echo  [ERREUR] config.xml introuvable.
    pause
    exit /b 1
)

if not exist scribe.db (
    echo  Initialisation de la base de donnees...
    python setup.py
    if errorlevel 1 (
        echo  [ERREUR] setup.py a echoue.
        pause
        exit /b 1
    )
)

echo.
echo  =====================================================
echo   SCRIBE pret. Demarrage sur http://localhost:8000
echo   Login    : voir config.xml
echo   Mobile   : http://localhost:8000/m
echo  =====================================================
echo.
echo  Ctrl+C pour arreter
echo.

python main.py
pause
