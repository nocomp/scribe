#!/usr/bin/env sh
set -euo pipefail

echo ""
echo "  ██████╗  ██████╗██████╗ ██╗██████╗ ███████╗"
echo "  ██╔════╝██╔════╝██╔══██╗██║██╔══██╗██╔════╝"
echo "  ╚█████╗ ██║     ██████╔╝██║██████╔╝█████╗  "
echo "   ╚═══██╗██║     ██╔══██╗██║██╔══██╗██╔══╝  "
echo "  ██████╔╝╚██████╗██║  ██║██║██████╔╝███████╗"
echo "  ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝"
echo "  Main courante de crise hospitalière — open source"
echo ""

# Lien symbolique base de données (au cas où le volume n'était pas monté au build)
mkdir -p /data/uploads /data/db
if [ ! -L /app/uploads ]; then
    rm -rf /app/uploads
    ln -sf /data/uploads /app/uploads
fi

# v2316 — Mode EXERCICE Docker : si SCRIBE_CONFIG est défini en env, on
# l'utilise directement sans chercher dans /data ni /app. Permet à
# docker-compose.exercice.yml de pointer chaque joueur vers son config_exo_*.xml
# et sa propre DB sans conflit.
if [ -n "${SCRIBE_CONFIG:-}" ] && [ -f "$SCRIBE_CONFIG" ]; then
    CONFIG_PATH="$SCRIBE_CONFIG"
    echo "  [config] Utilisation de $CONFIG_PATH (mode exercice/multi-instance)"
# Config XML : priorité à /data/config.xml (monté par volume), sinon /app/config.xml, sinon config_demo1.xml
elif [ -f /data/config.xml ]; then
    CONFIG_PATH=/data/config.xml
    echo "  [config] Utilisation de /data/config.xml"
elif [ -f /app/config.xml ]; then
    CONFIG_PATH=/app/config.xml
    echo "  [config] Utilisation de /app/config.xml"
elif [ -f /app/config_demo1.xml ]; then
    CONFIG_PATH=/app/config_demo1.xml
    echo "  [config] Utilisation de /app/config_demo1.xml (configuration par défaut) - ATTENTION cette instance utilise des données de démonstration"
    echo " Bien modifier les données avant passage en production"
else
    echo "  [config] ✗ Aucune configuration trouvée"
    exit 1
fi

# v2316 — DATABASE_URL et SCRIBE_CONFIG_JS configurables (mode exercice multi-instance)
# Si déjà fournis en env (par docker-compose.exercice.yml), on garde tels quels.
# Sinon, défaut prod = /data/db/scribe.db
if [ -z "${DATABASE_URL:-}" ]; then
    mkdir -p /data/db
    export DATABASE_URL="sqlite:////data/db/scribe.db"
fi
if [ -z "${SCRIBE_CONFIG_JS:-}" ]; then
    export SCRIBE_CONFIG_JS="/data/config.js"
fi
# Extraire le chemin du fichier DB depuis DATABASE_URL pour la détection
# "premier démarrage" — fonctionne pour sqlite:////chemin/abs et sqlite:///rel
DB_PATH=$(echo "$DATABASE_URL" | sed -E 's|^sqlite:////|/|; s|^sqlite:///||')

# Initialisation au premier démarrage
if [ ! -f "$DB_PATH" ]; then
    echo "  [init] Premier démarrage — initialisation..."
    python setup.py "$CONFIG_PATH"
    # Référentiel capacitaire (selon le mode)
    # Référentiel capacitaire
    python setup_capacite_demo.py 2>/dev/null || true
    if echo "$CONFIG_PATH" | grep -q "demo1\|demo2\|demo3\|demo4\|demo"; then
        python seed_demo_crise.py 2>/dev/null || true
        python seed_demo_comptes.py 2>/dev/null || true
        echo "  [init] Mode démo : scénario crise + comptes démo chargés."
    fi
    python seed.py 2>/dev/null || true
    echo "  [init] Base initialisée."
else
    echo "  [init] Base existante détectée — démarrage direct."
    # Migrations légères : s'assurer que les nouvelles tables existent
    python -c "
import sys; sys.path.insert(0,'.')
from app.database import engine, Base
import app.models
Base.metadata.create_all(bind=engine)
print('  [init] Tables vérifiées.')
"
fi

# Lien config.js généré vers /app/app/static/
if [ -f /data/config.js ]; then
    ln -sf /data/config.js /app/app/static/config.js
fi

# v2316 — Port d'écoute configurable via SCRIBE_PORT (mode exercice multi-instance).
# Défaut : 8000 (instance prod classique).
LISTEN_PORT="${SCRIBE_PORT:-8000}"

echo ""
echo "  ✓ SCRIBE démarré sur http://localhost:${LISTEN_PORT}"
echo "  ✓ DB : $DB_PATH"
echo "  ✓ Config : $CONFIG_PATH"
echo ""

# SQLite is not designed for high-concurrency writes; keep a single worker to avoid "database is locked" errors
exec uvicorn main:app --host 0.0.0.0 --port "$LISTEN_PORT" --workers 1
