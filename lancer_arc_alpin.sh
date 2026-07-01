#!/bin/bash
# SCRIBE v3.3.x (h33) — Réseau Démo — Lancement 4 GHT + Collecteur
# Usage: bash lancer_scribe_demo.sh [--reset]
#
# Lance 4 instances Réseau Démo sur ports 8000-8003 + collecteur prod 9000.
# Cohabite proprement avec le mode exercice (8660-8669 + collecteur 8565).
# Tous les logs → logs/  Le terminal reste silencieux.
#
# Cohabitation mode exercice :
#   - pkill ciblé via SCRIBE_PROD_MODE=1 (ne touche pas aux process exercice)
#   - Ports prod : 8000-8003 + 9000  ≠  Ports exo : 8660-8669 + 8565

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RESET=0
[ "$1" = "--reset" ] && RESET=1

# ── Python ───────────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.11 python3.10 python3.9 python3.8 python3 python; do
    command -v "$cmd" &>/dev/null && "$cmd" -c "import fastapi" 2>/dev/null && PYTHON="$cmd" && break
done
[ -z "$PYTHON" ] && echo "ERREUR: Python+fastapi introuvable" && exit 1

# ── Dossiers ─────────────────────────────────────────────────────────────────
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
mkdir -p "$SCRIPT_DIR/instances/chag" "$SCRIPT_DIR/instances/ghtlmb"
mkdir -p "$SCRIPT_DIR/instances/ghtsav" "$SCRIPT_DIR/instances/ghtad38"

echo ""
echo "  ================================================"
echo "   SCRIBE v3.3.0-alpha16 (h33) — ARC ALPIN"
echo "   Python : $($PYTHON --version 2>&1)"
[ $RESET -eq 1 ] && echo "   MODE RESET"
echo "   Logs   : $LOG_DIR/"
echo "  ================================================"
echo ""

# ── Arrêt propre des anciens processus (PROD uniquement) ─────────────────────
# pkill ciblé pour cohabiter avec le mode exercice. On ne tue que ce qui porte
# SCRIBE_PROD_MODE=1 ou le chemin spécifique collecteur/collecteur.py
# (≠ collecteur_exercice/collecteur_exercice.py).
echo "  Arrêt des processus précédents (prod uniquement)..."
pkill -f "SCRIBE_PROD_MODE=1" 2>/dev/null || true
pkill -f "collecteur/collecteur.py" 2>/dev/null || true
sleep 1
for PORT in 8000 8001 8002 8003 9000; do
    fuser -k ${PORT}/tcp 2>/dev/null || true
done
sleep 1

# ── Reset ────────────────────────────────────────────────────────────────────
if [ $RESET -eq 1 ]; then
    rm -f "$SCRIPT_DIR/scribe_chag.db" "$SCRIPT_DIR/scribe_ght2.db" \
          "$SCRIPT_DIR/scribe_ght3.db" "$SCRIPT_DIR/scribe_ght4.db"
    rm -f "$SCRIPT_DIR/instances/chag/config.js"   \
          "$SCRIPT_DIR/instances/ghtlmb/config.js" \
          "$SCRIPT_DIR/instances/ghtsav/config.js" \
          "$SCRIPT_DIR/instances/ghtad38/config.js"
    rm -f "$SCRIPT_DIR/collecteur/collecteur_data.json"
    rm -f "$SCRIPT_DIR/collecteur/collecteur_pending.json"
    rm -f "$SCRIPT_DIR/collecteur/collecteur_transferts.json"
    echo "  Bases supprimées (tokens collecteur préservés)"
fi

# ── Trap Ctrl+C (cleanup ciblé prod) ─────────────────────────────────────────
cleanup() {
    echo ""
    echo "  Arrêt en cours (prod uniquement)..."
    pkill -f "SCRIBE_PROD_MODE=1" 2>/dev/null || true
    pkill -f "collecteur/collecteur.py" 2>/dev/null || true
    sleep 1
    for PORT in 8000 8001 8002 8003 9000; do
        fuser -k ${PORT}/tcp 2>/dev/null || true
    done
    echo "  Services prod arrêtés (mode exercice préservé s'il tourne)."
    exit 0
}
trap cleanup INT TERM

# ── Pré-enrôlement des tokens GHT ─────────────────────────────────────────────
echo "  [0/5] Pré-enrôlement des tokens GHTs..."
"$PYTHON" "$SCRIPT_DIR/pre_enrol_scribe_demo.py" >> "$LOG_DIR/setup.log" 2>&1 \
    && echo "  Pré-enrôlement OK" \
    || echo "  WARN: pré-enrôlement échoué (voir logs/setup.log)"

# ── Collecteur prod (port 9000) ───────────────────────────────────────────────
echo "  [1/5] Collecteur (port 9000)..."
(cd "$SCRIPT_DIR/collecteur" && export SCRIBE_PROD_MODE=1 && "$PYTHON" collecteur.py >> "$LOG_DIR/collecteur.log" 2>&1) &

echo "  Attente collecteur..."
for i in $(seq 1 20); do
    "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health')" 2>/dev/null \
        && echo "  Collecteur prêt ✓ (${i}s)" && break
    sleep 1
done

# ── Fonction de lancement d'instance ─────────────────────────────────────────
# N'appelle JAMAIS setup.py (menu interactif). Utilise setup_demo2.py qui lit
# SCRIBE_CONFIG_FILE et SCRIBE_CONFIG_JS pour générer config.js de l'instance.
init_and_launch() {
    local SIGLE="$1"
    local CONFIG="$2"
    local DB="$3"
    local PORT="$4"
    local INIT_SCRIPT="$5"
    local CAPA_SCRIPT="$6"
    local SEED_SCRIPT="$7"
    local INST_DIR="$SCRIPT_DIR/instances/$SIGLE"
    local CONFIG_JS="$INST_DIR/config.js"
    local LOGFILE="$LOG_DIR/${SIGLE}.log"

    (
        cd "$SCRIPT_DIR"
        # Marqueur SCRIBE_PROD_MODE pour le pkill ciblé (cohabite avec exercice).
        export SCRIBE_PROD_MODE=1
        # v3000h26 — Mot de passe admin par défaut pour la démo Réseau Démo.
        # Sans cet export, auth.py génère un mdp aléatoire à chaque démarrage
        # et "Scribe2026!" est rejeté avec 401.
        export SCRIBE_ADMIN_PASS="Scribe2026!"
        export DATABASE_URL="sqlite:///$SCRIPT_DIR/$DB"
        export SCRIBE_PORT="$PORT"
        export SCRIBE_CONFIG_JS="$CONFIG_JS"
        export SCRIBE_CONFIG_FILE="$SCRIPT_DIR/$CONFIG"

        if [ ! -f "$SCRIPT_DIR/$DB" ]; then
            echo "[$(date '+%H:%M:%S')] Init DB $SIGLE depuis $CONFIG..." >> "$LOGFILE"
            "$PYTHON" "$SCRIPT_DIR/$INIT_SCRIPT" >> "$LOGFILE" 2>&1
            [ $? -ne 0 ] && echo "[$(date '+%H:%M:%S')] ERREUR init $SIGLE" >> "$LOGFILE"
            [ -n "$CAPA_SCRIPT" ] && [ -f "$SCRIPT_DIR/$CAPA_SCRIPT" ] && \
                "$PYTHON" "$SCRIPT_DIR/$CAPA_SCRIPT" >> "$LOGFILE" 2>&1
            [ -n "$SEED_SCRIPT" ] && [ -f "$SCRIPT_DIR/$SEED_SCRIPT" ] && \
                "$PYTHON" "$SCRIPT_DIR/$SEED_SCRIPT" >> "$LOGFILE" 2>&1
            "$PYTHON" "$SCRIPT_DIR/seed_demo_comptes.py" >> "$LOGFILE" 2>&1 || true
            "$PYTHON" "$SCRIPT_DIR/seed_uf_chag.py" "$SCRIPT_DIR/$DB" >> "$LOGFILE" 2>&1 || true
        else
            # DB existante : regénérer config.js si manquant
            if [ ! -f "$CONFIG_JS" ]; then
                echo "[$(date '+%H:%M:%S')] Regénération config.js $SIGLE..." >> "$LOGFILE"
                "$PYTHON" "$SCRIPT_DIR/$INIT_SCRIPT" >> "$LOGFILE" 2>&1
            fi
        fi

        echo "[$(date '+%H:%M:%S')] Démarrage $SIGLE → http://localhost:$PORT" >> "$LOGFILE"
        "$PYTHON" "$SCRIPT_DIR/main.py" >> "$LOGFILE" 2>&1
    ) &

    echo "  [$SIGLE] → http://localhost:$PORT  (logs: logs/${SIGLE}.log)"
}

# ── Lancement des 4 GHT ───────────────────────────────────────────────────────
# CHV utilise config_chag.xml en prod (vraies données) si présent,
# sinon config_chag_demo.xml en fallback démo.
CHAG_CONFIG="config_chag.xml"
[ ! -f "$SCRIPT_DIR/config_chag.xml" ] && CHAG_CONFIG="config_chag_demo.xml"

echo "  [2/5] CHV (port 8000)..."
init_and_launch "chag" "$CHAG_CONFIG" "scribe_chag.db" "8000" "setup_demo2.py" "setup_capacite_chag.py" ""
sleep 3

echo "  [3/5] GHT Lac Grandmont (port 8001)..."
init_and_launch "ghtlmb" "config_demo2.xml" "scribe_ght2.db" "8001" "setup_demo2.py" "setup_capacite_demo.py" "seed_demo_crise.py"
sleep 2

echo "  [4/5] GHT Savoie Belley (port 8002)..."
init_and_launch "ghtsav" "config_demo3.xml" "scribe_ght3.db" "8002" "setup_demo2.py" "setup_capacite_demo.py" "seed_demo_crise.py"
sleep 2

echo "  [5/5] GHT Alpes-Dauphiné (port 8003)..."
init_and_launch "ghtad38" "config_demo4.xml" "scribe_ght4.db" "8003" "setup_demo2.py" "setup_capacite_demo.py" "seed_demo_crise.py"

# ── Résumé ────────────────────────────────────────────────────────────────────
sleep 3
echo ""
echo "  ================================================"
echo "   Collecteur  : http://localhost:9000"
echo "   CHV        : http://localhost:8000"
echo "   GHT1      : http://localhost:8001"
echo "   GHT2      : http://localhost:8002"
echo "   GHT3     : http://localhost:8003"
echo "  ================================================"
echo ""
echo "  📋 Logs en temps réel :"
echo "     tail -f logs/chag.log"
echo "     tail -f logs/collecteur.log"
echo ""
echo "  Login : dircrise / Scribe2026!"
echo "  Supervision : http://localhost:9000"
echo "  Auth superv. : cd collecteur && python setup_collecteur_auth.py -u admin -p VotreMotDePasse"
echo ""
echo "  ✨ Nouveautés v3.3 (h33) :"
echo "     • Assistant copilote dans chaque instance (panneau 🎓)"
echo "     • Anti-spam escaladé + boutons d'aide ARS/ANSSI/CNIL"
echo "     • Modèles de messages réglementaires copiables"
echo "     • Hostname configurable via http://localhost:9000/setup_hostname.html"
echo ""
echo "  Ctrl+C pour tout arrêter (mode exercice préservé s'il tourne)"
echo "  Pour réinitialiser : bash lancer_scribe_demo.sh --reset"
echo ""

# ── Heartbeat silencieux ──────────────────────────────────────────────────────
while true; do
    sleep 30
    # Compter seulement les process avec SCRIBE_PROD_MODE pour distinguer
    # de ce qui tourne en mode exercice.
    RUNNING=$(pgrep -fc "SCRIBE_PROD_MODE=1" 2>/dev/null || echo 0)
    COLL=$(pgrep -fc "collecteur/collecteur.py" 2>/dev/null || echo 0)
    echo "  ♥  $(date '+%H:%M:%S') — instances prod: $RUNNING/4  collecteur: $COLL/1"
done
