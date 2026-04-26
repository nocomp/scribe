#!/bin/bash
# ============================================================
#  SCRIBE v1.4.0 — Collecteur territorial
#  Usage : bash lancer_collecteur.sh
# ============================================================

# Se placer dans le répertoire du script (même comportement que %~dp0 sous Windows)
cd "$(dirname "$0")"

echo ""
echo "  ============================================"
echo "   SCRIBE v1.4.0 — Collecteur territorial"
echo "   Port 9000"
echo "  ============================================"
echo ""

# Déterminer quelle commande Python utiliser
PYTHON=""
for cmd in python3.8 python3.9 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        # Vérifier que uvicorn est accessible depuis ce Python
        if "$cmd" -c "import uvicorn" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ERREUR: Aucun Python avec uvicorn trouvé."
    echo "  Installez les dépendances : python3.8 -m pip install -r collecteur_requirements.txt --user"
    exit 1
fi

echo "  Python utilisé : $($PYTHON --version 2>&1)"
echo ""

# Installer les dépendances si nécessaire
"$PYTHON" -m pip install -r collecteur_requirements.txt --user -q

echo "  Démarrage du collecteur..."
echo "  Dashboard : http://localhost:9000"
echo ""

"$PYTHON" collecteur.py
