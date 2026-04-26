#!/bin/bash
echo "Arrêt de tous les processus SCRIBE..."
pkill -9 -f "collecteur.py" 2>/dev/null
pkill -9 -f "main.py" 2>/dev/null
pkill -9 -f "uvicorn" 2>/dev/null
sleep 1
# Libérer les ports
for PORT in 8000 8001 8002 8003 9000; do
    fuser -k ${PORT}/tcp 2>/dev/null || true
done
echo "Ports libérés."
# Supprimer les anciens fichiers de données collecteur
# (dans TOUS les répertoires scribe possibles)
find ~ -name "collecteur_tokens.json" -path "*/collecteur/*" 2>/dev/null | while read f; do
    echo "Suppression: $f"
    rm -f "$f"
done
find ~ -name "collecteur_data.json" -path "*/collecteur/*" 2>/dev/null | while read f; do
    echo "Suppression: $f"  
    rm -f "$f"
done
find ~ -name "collecteur_pending.json" -path "*/collecteur/*" 2>/dev/null | while read f; do
    echo "Suppression: $f"
    rm -f "$f"
done
echo "Fait. Attente 2s..."
sleep 2
echo "Vérification ports:"
for PORT in 8000 8001 8002 8003 9000; do
    fuser ${PORT}/tcp 2>/dev/null && echo "  Port $PORT: encore occupé!" || echo "  Port $PORT: libre ✓"
done
