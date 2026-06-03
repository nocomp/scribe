#!/bin/bash
# SCRIBE v1.6.0 — Instance DÉMO permanente
# App : port 7474 | Collecteur : port 7373
# Reset automatique toutes les heures
# Usage: bash lancer_demo.sh [--stop]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_PORT=7474
COLL_PORT=7373
DEMO_DB="$SCRIPT_DIR/scribe_demo_perm.db"
DEMO_INST="$SCRIPT_DIR/instances/demo_perm"
DEMO_CONFIG="$SCRIPT_DIR/config.xml"
LOG_DIR="$SCRIPT_DIR/logs"
PIDFILE_APP="$SCRIPT_DIR/demo_app.pid"
PIDFILE_COLL="$SCRIPT_DIR/demo_coll.pid"

# Python
PYTHON=""
[ -f "$SCRIPT_DIR/venv/bin/python" ] && \
    "$SCRIPT_DIR/venv/bin/python" -c "import fastapi" 2>/dev/null && \
    PYTHON="$SCRIPT_DIR/venv/bin/python"
[ -z "$PYTHON" ] && for cmd in python3.11 python3.10 python3 python; do
    command -v "$cmd" &>/dev/null && "$cmd" -c "import fastapi" 2>/dev/null && \
        PYTHON="$cmd" && break
done
[ -z "$PYTHON" ] && echo "ERREUR: Python+fastapi introuvable" && exit 1

mkdir -p "$DEMO_INST" "$LOG_DIR"

if [ "$1" = "--stop" ]; then
    echo "Arrêt démo permanente..."
    [ -f "$PIDFILE_APP" ]  && kill "$(cat $PIDFILE_APP)"  2>/dev/null; rm -f "$PIDFILE_APP"
    [ -f "$PIDFILE_COLL" ] && kill "$(cat $PIDFILE_COLL)" 2>/dev/null; rm -f "$PIDFILE_COLL"
    fuser -k ${APP_PORT}/tcp  2>/dev/null || true
    fuser -k ${COLL_PORT}/tcp 2>/dev/null || true
    echo "Démo arrêtée."
    exit 0
fi

reset_demo() {
    echo "[$(date '+%H:%M:%S')] Reset démo..."
    fuser -k ${APP_PORT}/tcp 2>/dev/null || true
    sleep 2

    rm -f "$DEMO_DB" "$DEMO_INST/config.js"

    export DATABASE_URL="sqlite:///$DEMO_DB"
    export SCRIBE_PORT="$APP_PORT"
    export SCRIBE_CONFIG_JS="$DEMO_INST/config.js"
    export SCRIBE_CONFIG_FILE="$DEMO_CONFIG"

    cd "$SCRIPT_DIR"
    "$PYTHON" setup_demo2.py    >> "$LOG_DIR/demo_perm.log" 2>&1
    "$PYTHON" setup_capacite_demo.py >> "$LOG_DIR/demo_perm.log" 2>&1
    "$PYTHON" seed_demo_crise.py >> "$LOG_DIR/demo_perm.log" 2>&1
    "$PYTHON" seed_demo_comptes.py >> "$LOG_DIR/demo_perm.log" 2>&1

    # Corriger URL collecteur — pointer vers port 7373 (collecteur démo)
    sed -i "s|:9000/api/push|:7373/api/push|g" "$DEMO_INST/config.js" 2>/dev/null || true
    # Corriger URL collecteur si SCRIBE_HOST défini
    if [ -n "$SCRIBE_HOST" ]; then
        sed -i "s|http://localhost:${COLL_PORT}|http://$SCRIBE_HOST:${COLL_PORT}|g" \
            "$DEMO_INST/config.js" 2>/dev/null || true
    fi

    # Lancer l'app
    nohup bash -c "
        export DATABASE_URL=\"sqlite:///$DEMO_DB\"
        export SCRIBE_PORT=\"$APP_PORT\"
        export SCRIBE_CONFIG_JS=\"$DEMO_INST/config.js\"
        export SCRIBE_CONFIG_FILE=\"$DEMO_CONFIG\"
        # Propager la clé Albert si définie dans l'environnement parent
        [ -n \"$SCRIBE_IA_KEY\" ] && export SCRIBE_IA_KEY=\"$SCRIBE_IA_KEY\"
        [ -n \"$SCRIBE_IA_PROVIDER\" ] && export SCRIBE_IA_PROVIDER=\"$SCRIBE_IA_PROVIDER\"
        cd \"$SCRIPT_DIR\"
        exec \"$PYTHON\" main.py
    " >> "$LOG_DIR/demo_perm.log" 2>&1 &
    echo $! > "$PIDFILE_APP"
    echo "[$(date '+%H:%M:%S')] Démo redémarrée → http://localhost:$APP_PORT"
}

# Lancer le collecteur démo
echo "Démarrage collecteur démo (port $COLL_PORT)..."
fuser -k ${COLL_PORT}/tcp 2>/dev/null || true
sleep 1

# Config tokens pour la démo
COLL_DIR="$SCRIPT_DIR/collecteur_demo"
mkdir -p "$COLL_DIR"
cp "$SCRIPT_DIR/collecteur/collecteur.py" "$COLL_DIR/"
# Token démo unique
DEMO_TOKEN="demo_scribe_permanent_7474"
echo "{\"$DEMO_TOKEN\": \"DEMO\"}" > "$COLL_DIR/collecteur_tokens.json"

# Patch config.js démo avec le bon token collecteur
# (sera fait après init dans reset_demo)

nohup bash -c "
    cd \"$COLL_DIR\"
    COLLECTEUR_PORT=7373 exec \"$PYTHON\" collecteur.py
" >> "$LOG_DIR/demo_collecteur.log" 2>&1 &
echo $! > "$PIDFILE_COLL"
sleep 3

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   SCRIBE — Démo permanente v1.6.0           ║"
echo "  ╠══════════════════════════════════════════════╣"
echo "  ║  App        : http://localhost:$APP_PORT       ║"
echo "  ║  Collecteur : http://localhost:$COLL_PORT       ║"
echo "  ║  Reset      : toutes les heures             ║"
echo "  ║  Login      : dircrise / Scribe2026!        ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# Premier démarrage
reset_demo

# Boucle de reset toutes les heures
while true; do
    sleep 3600
    echo "[$(date '+%H:%M:%S')] Reset horaire démo..."
    reset_demo
done
