#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  SCRIBE v1.4.0 — Script de déploiement établissement (Linux)
#  Équivalent de SETUP.bat pour Linux/macOS
#  Usage : bash setup_etablissement.sh [config.xml] [--demo]
# ═══════════════════════════════════════════════════════════════════
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

CONFIG_FILE="${1:-config.xml}"
DEMO_MODE=0
[ "$2" = "--demo" ] || [ "$1" = "--demo" ] && DEMO_MODE=1
[ "$1" = "--demo" ] && CONFIG_FILE="config.xml"

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   SCRIBE v1.4.0 — Setup établissement        ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# ── Trouver Python ────────────────────────────────────────────────
PYTHON=""
for cmd in python3.8 python3.9 python3.10 python3.11 python3 python; do
    command -v "$cmd" &>/dev/null && "$cmd" -c "import sys; assert sys.version_info >= (3,8)" 2>/dev/null && PYTHON="$cmd" && break
done
[ -z "$PYTHON" ] && echo "  ERREUR: Python >= 3.8 introuvable" && exit 1
echo "  Python    : $($PYTHON --version 2>&1)"

# ── Vérifier les dépendances ──────────────────────────────────────
echo "  Vérification des dépendances..."
MISSING=""
for pkg in fastapi uvicorn sqlalchemy pydantic httpx openpyxl; do
    "$PYTHON" -c "import $pkg" 2>/dev/null || MISSING="$MISSING $pkg"
done

if [ -n "$MISSING" ]; then
    echo "  Installation des dépendances manquantes :$MISSING"
    "$PYTHON" -m pip install fastapi uvicorn sqlalchemy pydantic httpx openpyxl python-jose passlib --quiet
    if [ $? -ne 0 ]; then
        echo ""
        echo "  Essai avec --user..."
        "$PYTHON" -m pip install --user fastapi uvicorn sqlalchemy pydantic httpx openpyxl python-jose passlib --quiet
    fi
fi

# ── Vérifier config.xml ───────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/$CONFIG_FILE" ]; then
    echo ""
    echo "  ERREUR: $CONFIG_FILE introuvable dans $SCRIPT_DIR"
    echo ""
    echo "  Créez votre config.xml en vous basant sur config.xml.example"
    echo "  ou importez depuis Excel : python import_config_xlsx.py votre_config.xlsx"
    exit 1
fi

echo "  Config     : $CONFIG_FILE"

# ── Initialisation base de données ───────────────────────────────
DB_FILE=$(grep -o 'scribe[a-zA-Z0-9_]*\.db' "$SCRIPT_DIR/$CONFIG_FILE" 2>/dev/null || echo "scribe.db")
export DATABASE_URL="sqlite:///$SCRIPT_DIR/scribe.db"
export SCRIBE_CONFIG_FILE="$SCRIPT_DIR/$CONFIG_FILE"
export SCRIBE_CONFIG_JS="$SCRIPT_DIR/app/static/config.js"

echo ""
if [ ! -f "$SCRIPT_DIR/scribe.db" ]; then
    echo "  [1/4] Initialisation de la base de données..."
    "$PYTHON" setup.py "$SCRIPT_DIR/$CONFIG_FILE"
    if [ $? -ne 0 ]; then echo "  ERREUR lors de setup.py" && exit 1; fi
else
    echo "  [1/4] Mise à jour de la configuration..."
    "$PYTHON" setup.py "$SCRIPT_DIR/$CONFIG_FILE"
fi

# ── Import UF (si uf.xlsx présent) ────────────────────────────────
if [ -f "$SCRIPT_DIR/uf.xlsx" ]; then
    echo "  [2/4] Import des UF depuis uf.xlsx..."
    "$PYTHON" import_uf2.py uf.xlsx
else
    echo "  [2/4] UF : uf.xlsx absent — UF par défaut"
    "$PYTHON" setup_capacite_demo.py 2>/dev/null || true
fi

# ── Import comptes (si comptes.xlsx présent) ──────────────────────
if [ -f "$SCRIPT_DIR/comptes.xlsx" ]; then
    echo "  [3/4] Import des comptes depuis comptes.xlsx..."
    "$PYTHON" import_comptes.py comptes.xlsx
elif [ $DEMO_MODE -eq 1 ]; then
    echo "  [3/4] Mode démo : création des comptes de démonstration..."
    "$PYTHON" seed_demo_comptes.py
    "$PYTHON" seed_demo_crise.py 2>/dev/null || true
else
    echo "  [3/4] Comptes : créez des comptes via le panneau admin ou importez comptes.xlsx"
fi

# ── Résumé ────────────────────────────────────────────────────────
echo ""
echo "  [4/4] Vérification finale..."
"$PYTHON" -c "
import sqlite3, os
db = sqlite3.connect('scribe.db')
sites = db.execute('SELECT COUNT(*) FROM hospitals').fetchone()[0]
ufs   = db.execute('SELECT COUNT(*) FROM unites_fonctionnelles').fetchone()[0]
users = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
db.close()
print(f'  ✓ Sites   : {sites}')
print(f'  ✓ UF      : {ufs}')
print(f'  ✓ Comptes : {users}')
" 2>/dev/null

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   SCRIBE est prêt !                          ║"
echo "  ╠══════════════════════════════════════════════╣"
echo "  ║   Démarrer  : bash lancer_demo.sh            ║"
echo "  ║   Interface : http://localhost:8000           ║"
echo "  ║   Login     : dircrise / Scribe2026!          ║"
[ $DEMO_MODE -eq 1 ] && \
echo "  ║   Démo mdp  : Demo2026! (à changer)          ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
