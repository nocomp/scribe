#!/bin/bash
# SCRIBE — Audit de sécurité automatique
# Lance pip-audit + bandit + checks manuels

set -e
cd "$(dirname "$0")/.."

echo "=== 1. pip-audit (CVE des dépendances) ==="
pip install --quiet pip-audit 2>/dev/null || true
pip-audit -r requirements.txt || echo "⚠ Vulnérabilités détectées (voir ci-dessus)"

echo ""
echo "=== 2. bandit (analyse statique Python) ==="
pip install --quiet bandit 2>/dev/null || true
bandit -q -r app/ master/ collecteur/ collecteur_exercice/ plugins/ core/ -ll || echo "⚠ Issues bandit détectées"

echo ""
echo "=== 3. Vérifications manuelles ==="
echo "--- Variables d'environnement requises ---"
for var in SCRIBE_SECRET SCRIBE_ADMIN_PASS; do
    if [ -z "${!var}" ]; then
        echo "  ⚠ $var non défini (utiliser secrets aléatoires en prod)"
    else
        echo "  ✓ $var défini"
    fi
done

echo ""
echo "--- Permissions fichiers sensibles ---"
for f in data/.scribe_secret collecteur/collecteur_admin.json; do
    if [ -f "$f" ]; then
        perms=$(stat -c %a "$f" 2>/dev/null || stat -f %A "$f" 2>/dev/null)
        if [ "$perms" = "600" ]; then
            echo "  ✓ $f : 600"
        else
            echo "  ⚠ $f : $perms (recommandé : 600)"
        fi
    fi
done

echo ""
echo "=== Fin audit ==="
