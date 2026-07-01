#!/usr/bin/env python3
"""
patch_federation.py — Correctif SCRIBE v1.4.0
Corrige le bug de duplication dans app/api/federation.py
qui empêche les GHTs de pousser vers le collecteur.

Usage: python3 patch_federation.py
Puis redémarrer les instances SCRIBE.
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
fed_path = os.path.join(BASE, 'app', 'api', 'federation.py')

if not os.path.exists(fed_path):
    print(f"ERREUR: {fed_path} non trouvé")
    sys.exit(1)

content = open(fed_path, encoding='utf-8').read()
lines = content.split('\n')
print(f"federation.py actuel: {len(lines)} lignes")

class_count = sum(1 for l in lines if l.startswith('class FederationConfig'))
loop_count  = sum(1 for l in lines if 'async def federation_loop' in l)

print(f"  FederationConfig: {class_count}x  |  federation_loop: {loop_count}x")

if class_count <= 1 and loop_count <= 1:
    print("✓ Pas de duplication — fichier correct")
    sys.exit(0)

print(f"⚠ Duplication détectée — correction en cours...")

# Trouver la 2ème occurrence de class FederationConfig
first_idx = None
second_idx = None
for i, l in enumerate(lines):
    if l.startswith('class FederationConfig'):
        if first_idx is None:
            first_idx = i
        else:
            second_idx = i
            break

if second_idx is None:
    print("Structure inattendue — recherche par federation_loop")
    loop_indices = [i for i, l in enumerate(lines) if 'async def federation_loop' in l]
    if len(loop_indices) >= 2:
        second_idx = loop_indices[1]

if second_idx is None:
    print("Impossible de localiser la duplication — patch annulé")
    sys.exit(1)

print(f"Suppression des lignes {second_idx+1}–{len(lines)}")
clean_lines = lines[:second_idx]
clean_content = '\n'.join(clean_lines)

# Ajouter build_capacite_payload si absent
if 'def build_capacite_payload' not in clean_content:
    clean_content += '''

def build_capacite_payload(db, cfg) -> dict:
    try:
        from app.models import CapaciteReferentiel
        refs = db.query(CapaciteReferentiel).all()
        return {
            "etablissement": {"nom": cfg.etablissement_nom, "sigle": cfg.etablissement_sigle},
            "synthese": [], "alertes": [], "nb_services": len(refs), "nb_alertes": 0,
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
    except Exception:
        return {}


async def push_capacite_to_collecteur(cfg, payload: dict) -> bool:
    if not cfg.is_ready or not payload:
        return False
    try:
        import httpx
        cap_url = cfg.collecteur_url.replace("/api/push", "/api/push-capacite")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(cap_url, json=payload,
                headers={"Authorization": f"Bearer {cfg.token}"})
            return resp.status_code in (200, 201, 204)
    except Exception:
        return False
'''

# Vérifier syntaxe
try:
    compile(clean_content, 'federation.py', 'exec')
except SyntaxError as e:
    print(f"ERREUR syntaxe après patch: {e}")
    sys.exit(1)

# Sauvegarder l'original
import shutil
backup = fed_path + '.bak'
shutil.copy2(fed_path, backup)
print(f"Backup: {backup}")

open(fed_path, 'w', encoding='utf-8').write(clean_content)
final_lines = clean_content.count('\n') + 1
print(f"✓ Corrigé: {final_lines} lignes (était {len(lines)})")
print()
print("Redémarrer les instances SCRIBE:")
print("  bash lancer_scribe.sh")
print("  (sans --reset pour préserver les données)")
