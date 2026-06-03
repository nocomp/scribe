#!/bin/bash
# tests/bench/run_bench.sh — Lance le benchmark SCRIBE.
#
# Vérifie les prérequis (Python + dépendances), puis lance bench.py depuis
# la racine du projet. Affiche une aide claire en cas d'erreur.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIBE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$SCRIBE_ROOT"

# ── Choix de l'interpréteur Python ──
PYTHON=""
for cmd in python3.11 python3.10 python3.9 python3.8 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import fastapi, httpx, sqlalchemy, uvicorn" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo ""
    echo "  ERREUR : Python avec fastapi/httpx/sqlalchemy/uvicorn introuvable."
    echo ""
    echo "  Installez les prérequis :"
    echo "    pip install fastapi httpx sqlalchemy uvicorn"
    echo ""
    exit 1
fi

echo ""
echo "  Python        : $($PYTHON --version 2>&1)"
echo "  SCRIBE root   : $SCRIBE_ROOT"
echo ""

# ── Vérification rapide : pas d'instance déjà lancée sur 17900-17902 ──
for port in 17900 17901 17902; do
    if command -v lsof &>/dev/null; then
        if lsof -iTCP:$port -sTCP:LISTEN &>/dev/null; then
            echo "  ERREUR : le port $port est déjà utilisé."
            echo "  Le benchmark a besoin des ports 17900, 17901, 17902 libres."
            echo "  Commande pour trouver le process : lsof -iTCP:$port -sTCP:LISTEN"
            exit 2
        fi
    fi
done

# ── Lancer le bench ──
exec "$PYTHON" "$SCRIPT_DIR/bench.py" "$@"
