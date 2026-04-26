#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# lancer_exercice.sh — SCRIBE Mode Exercice multi-sites
#
# Lance un exercice de gestion de crise simulant 6 établissements de santé
# fictifs + un collecteur animateur (poste de l'animateur d'exercice).
#
# Le collecteur (port 8565) sert d'interface animateur :
#   - Charge un scénario d'exercice (séquence d'événements horodatés)
#   - Pousse les stimuli (incidents, messages, tensions capacité…) aux
#     sites concernés
#   - Centralise la supervision des 6 sites
#
# Les 6 sites (ports 8660-8665) sont des instances SCRIBE classiques en
# mode exercice (DB isolée, mention "EXERCICE — Données fictives").
#
# Usage :
#   bash lancer_exercice.sh             # lance tout
#   bash lancer_exercice.sh --reset     # reset DBs + state collecteur
#   bash lancer_exercice.sh --sites="CH_NORD,CH_SUD"   # sites spécifiques
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RESET=0
SITES_FILTER=""
for arg in "$@"; do
    [ "$arg" = "--reset" ] && RESET=1
    [[ "$arg" == --sites=* ]] && SITES_FILTER="${arg#--sites=}"
done

PYTHON=""
[ -f "$SCRIPT_DIR/venv/bin/python" ] && \
    "$SCRIPT_DIR/venv/bin/python" -c "import fastapi" 2>/dev/null && \
    PYTHON="$SCRIPT_DIR/venv/bin/python"
if [ -z "$PYTHON" ]; then
    for cmd in python3.11 python3.10 python3.9 python3.12 python3 python; do
        command -v "$cmd" &>/dev/null && "$cmd" -c "import fastapi" 2>/dev/null && \
            PYTHON="$cmd" && break
    done
fi
[ -z "$PYTHON" ] && echo "ERREUR: Python+fastapi introuvable. Lancez d'abord : pip install -r requirements.txt" && exit 1

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
mkdir -p "$SCRIPT_DIR/collecteur_exercice"

echo ""
echo "  =============================================================="
echo "   SCRIBE — EXERCICE DE CRISE MULTI-SITES"
echo "   Python : $($PYTHON --version 2>&1)"
[ $RESET -eq 1 ] && echo "   MODE RESET — bases exercice supprimees"
[ -n "$SITES_FILTER" ] && echo "   Sites filtres : $SITES_FILTER"
echo "  =============================================================="
echo ""

pkill -f "SCRIBE_EXERCICE_MODE=1" 2>/dev/null || true
for PORT in 8565 8660 8661 8662 8663 8664 8665; do
    fuser -k ${PORT}/tcp 2>/dev/null || true
done
sleep 1

if [ $RESET -eq 1 ]; then
    rm -f "$SCRIPT_DIR"/scribe_exo_*.db
    rm -f "$SCRIPT_DIR"/scribe_exo_*.db-journal
    rm -f "$SCRIPT_DIR"/collecteur_exercice/collecteur_exo_*.json
    if [ -d "$SCRIPT_DIR/scenarios" ]; then
        find "$SCRIPT_DIR/scenarios" -maxdepth 1 -name "*.json" ! -name "example_*.json" -delete 2>/dev/null || true
    fi
    echo "  DBs exercice + etat collecteur supprimes"
fi

cleanup() {
    echo ""
    echo "  Arret exercice..."
    pkill -f "SCRIBE_EXERCICE_MODE=1" 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

echo "  [1/7] Collecteur exercice (port 8565)..."
(
    cd "$SCRIPT_DIR/collecteur_exercice"
    export SCRIBE_EXERCICE_MODE=1
    export COLLECTEUR_PORT=8565
    "$PYTHON" collecteur_exercice.py >> "$LOG_DIR/collecteur_exercice.log" 2>&1
) &
for i in $(seq 1 20); do
    "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://localhost:8565/health')" 2>/dev/null \
        && echo "  Collecteur exercice pret (${i}s)" && break
    sleep 1
done

init_and_launch_exo() {
    local SIGLE="$1" CONFIG="$2" DB="$3" PORT="$4"

    if [ -n "$SITES_FILTER" ]; then
        echo "$SITES_FILTER" | grep -q "$SIGLE" || { echo "  [skip] $SIGLE"; return 0; }
    fi

    local LOGFILE="$LOG_DIR/exo_${SIGLE}.log"

    (
        cd "$SCRIPT_DIR"
        export DATABASE_URL="sqlite:///$SCRIPT_DIR/$DB"
        export SCRIBE_PORT="$PORT"
        export SCRIBE_CONFIG_FILE="$SCRIPT_DIR/$CONFIG"
        export SCRIBE_EXERCICE_MODE="1"
        export SCRIBE_EXO_SIGLE="$SIGLE"
        export SCRIBE_EXO_COLLECTEUR="http://localhost:8565"
        export SCRIBE_ADMIN_USER="dircrise"
        export SCRIBE_ADMIN_PASS="Exercice2026!"

        if [ ! -f "$SCRIPT_DIR/$DB" ]; then
            echo "[$(date '+%H:%M:%S')] Init $SIGLE EXO..." >> "$LOGFILE"
            "$PYTHON" "$SCRIPT_DIR/setup.py" >> "$LOGFILE" 2>&1
        fi

        echo "[$(date '+%H:%M:%S')] Demarrage $SIGLE EXO -> :$PORT" >> "$LOGFILE"
        "$PYTHON" "$SCRIPT_DIR/main.py" >> "$LOGFILE" 2>&1
    ) &
    echo "  [$SIGLE] -> http://localhost:$PORT"
}

echo "  [2/7] CH_NORD (port 8660)..."
init_and_launch_exo "CH_NORD"        "config_exo_ch_nord.xml"        "scribe_exo_ch_nord.db"        "8660"
sleep 2

echo "  [3/7] CH_SUD (port 8661)..."
init_and_launch_exo "CH_SUD"         "config_exo_ch_sud.xml"         "scribe_exo_ch_sud.db"         "8661"
sleep 2

echo "  [4/7] CHU_CENTRE (port 8662)..."
init_and_launch_exo "CHU_CENTRE"     "config_exo_chu_centre.xml"     "scribe_exo_chu_centre.db"     "8662"
sleep 2

echo "  [5/7] CH_EST (port 8663)..."
init_and_launch_exo "CH_EST"         "config_exo_ch_est.xml"         "scribe_exo_ch_est.db"         "8663"
sleep 2

echo "  [6/7] CH_OUEST (port 8664)..."
init_and_launch_exo "CH_OUEST"       "config_exo_ch_ouest.xml"       "scribe_exo_ch_ouest.db"       "8664"
sleep 2

echo "  [7/7] CLINIQUE_DEMO (port 8665)..."
init_and_launch_exo "CLINIQUE_DEMO"  "config_exo_clinique_demo.xml"  "scribe_exo_clinique_demo.db"  "8665"

sleep 5
echo ""
echo "  =============================================================="
echo "   EXERCICE EN COURS"
echo "  --------------------------------------------------------------"
echo "   ANIMATEUR        : http://localhost:8565"
echo "  --------------------------------------------------------------"
echo "   CH_NORD          : http://localhost:8660"
echo "   CH_SUD           : http://localhost:8661"
echo "   CHU_CENTRE       : http://localhost:8662"
echo "   CH_EST           : http://localhost:8663"
echo "   CH_OUEST         : http://localhost:8664"
echo "   CLINIQUE_DEMO    : http://localhost:8665"
echo "  --------------------------------------------------------------"
echo "   Login joueur     : dircrise / Exercice2026!"
echo "   Login animateur  : animateur / Animateur2026! (:8565)"
echo "   Vue mobile       : http://localhost:8660/m"
echo "  =============================================================="
echo ""
echo "  Ctrl+C pour arreter l'exercice."
echo ""

while true; do
    sleep 60
    RUNNING=$(pgrep -c -f "SCRIBE_EXERCICE_MODE=1" 2>/dev/null || echo 0)
    echo "  ♥  $(date '+%H:%M:%S') — instances actives : $RUNNING"
done
