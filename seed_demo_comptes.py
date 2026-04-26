"""
seed_demo_comptes.py — Comptes de démonstration SCRIBE
Convention : <service>_demo_<sigle_ght>  (ex: dsi_demo_chag, urgences_demo_ghtlmb)
Pour les sites secondaires : <service>_demo_<site_court>  (ex: urgences_demo_stjulien)
Mot de passe : Demo2026!  (changement imposé à la 1ère connexion)
"""
import sys, os, hashlib
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
import app.models
from app.models import User, Hospital

BASE_PASSWORD = "Demo2026!"
hashed_pw = hashlib.sha256(BASE_PASSWORD.encode()).hexdigest()

db = SessionLocal()

# ── Lire le sigle de l'établissement depuis config.js ──────────────────────
import json, pathlib
sigle = "etab"
nom_etab = "Établissement"
config_js_path = os.environ.get("SCRIBE_CONFIG_JS", os.path.join(os.path.dirname(__file__), "app", "static", "config.js"))
try:
    raw = pathlib.Path(config_js_path).read_text(encoding="utf-8")
    start = raw.find("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
    cfg = json.loads(raw[start:raw.rfind(";")])
    sigle    = cfg.get("etablissement", {}).get("sigle", "etab").lower().replace("-","").replace(" ","")
    nom_etab = cfg.get("etablissement", {}).get("nom", "Établissement")
except Exception:
    pass

# Fallback: lire depuis config.xml si config.js absent/illisible
if sigle == "etab":
    xml_path = os.environ.get("SCRIBE_CONFIG_FILE", os.path.join(os.path.dirname(__file__), "config.xml"))
    try:
        import xml.etree.ElementTree as _ET
        _root = _ET.parse(xml_path).getroot()
        _etab = _root.find("etablissement")
        if _etab is not None:
            sigle    = (_etab.findtext("sigle") or "etab").strip().lower().replace("-","").replace(" ","")
            nom_etab = (_etab.findtext("nom")   or "Établissement").strip()
    except Exception:
        pass

print(f"\n  Établissement : {nom_etab} ({sigle.upper()})")

sites = db.query(Hospital).order_by(Hospital.id).all()
if not sites:
    print("  Aucun site — exécuter setup.py d'abord")
    sys.exit(1)

created = skipped = 0

def add_user(username, display_name, role="directeur"):
    global created, skipped
    username = username[:40]
    if db.query(User).filter_by(username=username).first():
        skipped += 1
        return
    try:
        db.add(User(username=username, display_name=display_name[:80],
                    role=role, hashed_password=hashed_pw,
                    active=True, must_change_password=True))
        db.flush()  # Detect UNIQUE constraint immediately
        created += 1
    except Exception:
        db.rollback()
        skipped += 1

def site_tag(site_nom, index):
    """Génère un tag court pour un site (max 12 chars)."""
    import unicodedata, re
    s = unicodedata.normalize("NFD", site_nom.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]", "_", s)
    # Prendre les mots significatifs
    words = [w for w in s.split("_") if len(w) > 2 and w not in
             ("site", "hopital", "centre", "chu", "ch", "du", "de", "la", "les",
              "saint", "clinique", "etablissement", "principal", "secondaire",
              "formation", "blanchisserie")]
    if not words:
        # Fallback: take last meaningful word from all words
        all_words = [w for w in s.split("_") if len(w) > 2]
        words = all_words[-2:] if len(all_words) >= 2 else all_words
    # Prendre les 2 DERNIERS mots significatifs (plus spécifiques)
    tag = "_".join(words[-2:])[:14] if words else f"site{index+1}"
    return tag

# ── Services par type d'établissement ─────────────────────────────────────
# Comptes de messagerie = 1 par pôle CHAG (affichés dans l'onglet SOINS)
# + comptes transverses
SERVICES_POLES_PRINCIPAL = [
    "urgences",      # pôle URGENCES
    "soins_critiques",  # pôle SOINS CRITIQUES
    "medecine",      # pôle MEDECINE
    "chirurgie",     # pôle CHIRURGIE ANESTHESIE
    "cardiovasculaire",  # pôle CARDIOVASCULAIRE
    "cancerologie",  # pôle CANCEROLOGIE
    "geriatrie",     # pôle GERIATRIE
    "fme",           # pôle FME (Femme Mère Enfant)
    "sante_mentale", # pôle SANTE MENTALE
    "sante_publique",# pôle SANTE PUBLIQUE
    "medico_technique",  # pôle MEDICO-TECHNIQUE
    "support",       # pôle SUPPORT
]
SERVICES_POLES_SECONDAIRE = [
    "urgences", "medecine", "chirurgie", "support",
]
# Alias pour compat
SERVICES_MCO = SERVICES_POLES_PRINCIPAL
SERVICES_PSY = ["psychiatrie", "addictologie", "cmp", "cadre_nuit"]
SERVICES_SSR = ["ssr", "geriatrie", "kinesitherapie", "cadre_nuit"]
SERVICES_SUPPORT = ["dsi", "daf", "drh", "direction", "qualite", "securite", "com"]
CELLULE = ["direction", "dsi", "daf", "drh", "com", "securite", "qualite", "logistique"]

print(f"  Sites : {len(sites)}")

# ── Comptes par site ────────────────────────────────────────────────────────
main_site = sites[0]
main_tag  = sigle  # site principal = sigle du GHT (ex: chag, ghtlmb)

for idx, site in enumerate(sites):
    tag = main_tag if idx == 0 else site_tag(site.nom, idx)
    nom_court = site.nom

    # Détecter le type de site
    nom_l = site.nom.lower()
    # Site principal: tous les pôles / Sites secondaires: pôles prioritaires
    services = SERVICES_POLES_PRINCIPAL if idx == 0 else SERVICES_POLES_SECONDAIRE

    for svc in services:
        label = svc.replace('_',' ').title()
        add_user(f"{svc}_demo_{tag}", f"{label} — {nom_court}", "directeur")

    # Cadre de garde pour chaque site
    add_user(f"cadre_demo_{tag}", f"Cadre de garde — {nom_court}", "directeur")

# ── Comptes transverses (indépendants du site) ──────────────────────────────
print("\n  Comptes transverses...")
add_user(f"dircrise_demo_{sigle}",    f"Directeur de Crise — {nom_etab}",   "admin")
add_user(f"direction_demo_{sigle}",   f"Direction Générale — {nom_etab}",   "directeur")
add_user(f"dsi_demo_{sigle}",         f"DSI — {nom_etab}",                  "directeur")
add_user(f"rssi_demo_{sigle}",        f"RSSI — {nom_etab}",                 "directeur")
add_user(f"drh_demo_{sigle}",         f"DRH — {nom_etab}",                  "directeur")
add_user(f"daf_demo_{sigle}",         f"DAF — {nom_etab}",                  "directeur")
add_user(f"observateur_demo_{sigle}", f"Observateur — {nom_etab}",          "observateur")
add_user(f"certsa_demo_{sigle}",      f"CERT Santé — {nom_etab}",           "observateur")
add_user(f"ars_demo_{sigle}",         f"ARS ARA — {nom_etab}",              "observateur")
add_user(f"communication_demo_{sigle}",f"Communication — {nom_etab}",       "directeur")

db.commit()
db.close()

print(f"\n  ✓ {created} compte(s) créé(s)  |  {skipped} déjà existant(s)")
print(f"  Login  : <service>_demo_{sigle}  (ex: dsi_demo_{sigle}, urgences_demo_{sigle})")
print(f"  Mot de passe : {BASE_PASSWORD}  (changement imposé à la 1ère connexion)")
