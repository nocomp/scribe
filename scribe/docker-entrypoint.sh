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

# Config XML : priorité à /data/config.xml (monté par volume), sinon /app/config.xml, sinon config_demo1.xml
if [ -f /data/config.xml ]; then
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

# Base SQLite : stocker dans /data/db/
export DATABASE_URL="sqlite:////data/db/scribe.db"

# Initialisation au premier démarrage
if [ ! -f /data/db/scribe.db ]; then
    echo "  [init] Premier démarrage — initialisation..."
    python setup.py "$CONFIG_PATH"
    # Référentiel capacitaire (selon le mode)
    if echo "$CONFIG_PATH" | grep -q "demo1\|demo"; then
        python setup_capacite_demo.py 2>/dev/null || true
        python seed_demo_crise.py 2>/dev/null || true
        echo "  [init] Mode démo : référentiel capacitaire + scénario crise chargés."
    else
        python setup_capacite_demo.py 2>/dev/null || true
        echo "  [init] Référentiel capacitaire générique chargé."
        echo "  [init] Pour votre référentiel : python setup_capacite_chag.py (CHAG)"
        echo "  [init]                          python import_config_xlsx.py (Excel)"
    fi
    python seed.py
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

echo ""
echo "  ✓ SCRIBE démarré sur http://localhost:8000"
echo "  ✓ Données persistantes dans /data/"
echo ""

# SQLite is not designed for high-concurrency writes; keep a single worker to avoid "database is locked" errors
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
