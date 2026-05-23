#!/bin/bash
# ── SCRIBE v2.1.0-master — Script unique de lancement ─────────────────────
# Lance UNIQUEMENT la supervision (collecteur :9000) avec le module master
# intégré. Les instances SCRIBE sont ensuite pilotées depuis l'UI :
#
#   http://localhost:9000  →  Onglet "📦 INSTANCES"
#
# Pré-rempli : 10 instances (8000-8009). L'admin lance celles dont il a
# besoin, configure adresse/géoloc/credentials, et clique ▶ LANCER.
# ──────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

# v2.4.8.4 — Support de l'option --reset pour repartir d'un état propre
if [ "$1" = "--reset" ] || [ "$1" = "-r" ]; then
    echo ""
    echo "  ╔══════════════════════════════════════════════════════════════╗"
    echo "  ║  SCRIBE — RESET COMPLET                                     ║"
    echo "  ╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  Va supprimer :"
    echo "    • master/.onboarding_done    (flag onboarding)"
    echo "    • master/.wizard_force       (flag wizard)"
    echo "    • master/master_instances*.json (state des instances)"
    echo "    • data/instances/*           (toutes les DBs d'instances)"
    echo "    • logs/*                     (anciens logs)"
    echo ""
    echo "  Les comptes de supervision et les configs racine sont préservés."
    echo ""
    read -r -p "  Confirmer le reset (oui/N) ? " CONFIRM
    if [ "$CONFIRM" != "oui" ] && [ "$CONFIRM" != "OUI" ]; then
        echo ""
        echo "  Annulé. SCRIBE n'a pas été lancé."
        exit 0
    fi
    echo ""
    echo "  [reset] Suppression des flags onboarding..."
    rm -f master/.onboarding_done master/.wizard_force
    echo "  [reset] Suppression du state des instances..."
    rm -f master/master_instances.json master/master_instances_exercice.json
    echo "  [reset] Suppression des DBs d'instances..."
    rm -rf data/instances/* data/instances_exercice/* 2>/dev/null || true
    echo "  [reset] Nettoyage des logs..."
    rm -f logs/*.log 2>/dev/null || true
    echo "  [reset] ✓ OK. SCRIBE va se relancer dans un état propre."
    echo ""
fi

# ── Bannière ──
cat << 'EOF'

  ╔══════════════════════════════════════════════════════════════╗
  ║  SCRIBE — Supervision avec pilotage d'instances             ║
  ║                                                              ║
  ║  http://localhost:9000  →  Onglet "📦 INSTANCES"            ║
  ║                                                              ║
  ║  Lancez/configurez vos instances depuis l'admin web.        ║
  ║  Ctrl+C pour arrêter (toutes les instances filles aussi).   ║
  ╚══════════════════════════════════════════════════════════════╝

EOF

# ── Vérifications ──
if ! command -v $PYTHON_BIN >/dev/null 2>&1; then
    echo "  ✗ Python 3 non trouvé. Installez Python 3.10+."
    exit 1
fi

PY_VER=$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  [info] Python $PY_VER"

# ── Dépendances ──
if [ -f "requirements.txt" ]; then
    echo "  [info] Vérification des dépendances..."
    $PYTHON_BIN -m pip install -q -r requirements.txt 2>&1 | grep -v "already satisfied" || true
fi

if [ -f "collecteur/collecteur_requirements.txt" ]; then
    $PYTHON_BIN -m pip install -q -r collecteur/collecteur_requirements.txt 2>&1 | grep -v "already satisfied" || true
fi

# ── Init répertoires ──
mkdir -p data/instances logs

# ── Vérifier le profil de base ──
if [ ! -f "master/profil_base.xlsx" ]; then
    if [ -f "SCRIBE_config_etablissement.xlsx" ]; then
        echo "  [setup] Copie du profil de base..."
        cp SCRIBE_config_etablissement.xlsx master/profil_base.xlsx
    else
        echo "  ⚠ Profil de base absent (master/profil_base.xlsx)"
        echo "    Vous pourrez l'uploader depuis l'UI ensuite."
    fi
fi

# ── Lancer le collecteur ──
echo ""
echo "  ▶ Démarrage de la supervision sur :9000..."
echo ""

cd collecteur
exec $PYTHON_BIN collecteur.py
