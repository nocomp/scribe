"""
apply_setup_config.py — Applique la configuration IA + fédération
Appelé par SETUP.bat après la saisie interactive des paramètres.
Lit les variables d'environnement définies par le BAT et met à jour config.js.
"""
import os, sys, re

config_js_path = os.path.join(os.path.dirname(__file__), 'app', 'static', 'config.js')
if not os.path.exists(config_js_path):
    print("[WARN] config.js introuvable - sera généré au prochain setup.py")
    sys.exit(0)

with open(config_js_path, 'r', encoding='utf-8') as f:
    cjs = f.read()

changes = []

# ── IA ──────────────────────────────────────────────────────────────
ia_fournisseur = os.environ.get('IA_FOURNISSEUR', '').strip()
ia_key         = os.environ.get('IA_KEY', '').strip()
ia_url         = os.environ.get('IA_URL', '').strip()
ia_model       = os.environ.get('IA_MODEL', '').strip()

if ia_fournisseur and ia_fournisseur != '4':
    if ia_fournisseur in ('albert','openai','anthropic','mistral','gemini','ollama','openai_compat'):
        cjs = re.sub(r'(ia_fournisseur\s*:\s*")[^"]*(")', f'\\g<1>{ia_fournisseur}\\2', cjs)
        changes.append(f"IA: {ia_fournisseur}")
    if ia_key and ia_key != 'none':
        cjs = re.sub(r'(ia_cle_api\s*:\s*")[^"]*(")', f'\\g<1>{ia_key}\\2', cjs)
        changes.append("cle API configuree")
    if ia_url:
        cjs = re.sub(r'(ia_url_base\s*:\s*")[^"]*(")', f'\\g<1>{ia_url}\\2', cjs)
    if ia_model:
        cjs = re.sub(r'(ia_modele\s*:\s*")[^"]*(")', f'\\g<1>{ia_model}\\2', cjs)

# ── FEDERATION ──────────────────────────────────────────────────────
fed_enabled = os.environ.get('FED_ENABLED', 'false').strip().lower()
fed_ip      = os.environ.get('FED_IP', '').strip()
fed_port    = os.environ.get('FED_PORT', '9000').strip()
fed_token   = os.environ.get('FED_TOKEN', '').strip()
sync_crise  = os.environ.get('SYNC_CRISE', 'false').strip().lower()
sync_sanit  = os.environ.get('SYNC_SANITAIRE', 'false').strip().lower()

if fed_enabled == 'true' and fed_ip:
    url_push = f'http://{fed_ip}:{fed_port}/api/push'
    cjs = re.sub(r'(federation_enabled\s*:\s*)[^,\n]+', r'\g<1>true', cjs)
    cjs = re.sub(r'(collecteur_url\s*:\s*")[^"]*(")', f'\\g<1>{url_push}\\2', cjs)
    if fed_token:
        cjs = re.sub(r'(federation_token\s*:\s*")[^"]*(")', f'\\g<1>{fed_token}\\2', cjs)
    cjs = re.sub(r'(sync_crise\s*:\s*)[^,\n]+', f'\\g<1>{sync_crise}', cjs)
    cjs = re.sub(r'(sync_sanitaire\s*:\s*)[^,\n]+', f'\\g<1>{sync_sanit}', cjs)
    changes.append(f"federation → {fed_ip}:{fed_port}")
    if sync_crise == 'true': changes.append("sync crise")
    if sync_sanit == 'true': changes.append("sync sanitaire")

with open(config_js_path, 'w', encoding='utf-8') as f:
    f.write(cjs)

if changes:
    for c in changes:
        print(f"  [OK] {c}")
else:
    print("  [OK] Aucune modification (pas de parametre saisi)")
