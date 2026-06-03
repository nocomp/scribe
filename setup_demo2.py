"""
setup_demo2.py — Initialisation DÉMO — Établissement 2
Clinique Saint-Benoît de Montrelay (CSBM)
GPS : secteur sud-est du territoire (rayon ~45 km du centre)

Usage : python setup_demo2.py
Ce script recrée la base de zéro avec des données anonymisées pour démonstration.
"""
import sys, os, json, hashlib
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
import app.models
import app.api.status_page
from app.models import Hospital, UniteFonctionnelle, User

# ── 1. Tables ──────────────────────────────────────────────────────────────
print("\n[1/5] Création de la base de données...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print("      ✓ Base recréée")

db = SessionLocal()

# ── 2. Sites — lus depuis config.xml ───────────────────────────────────────
print("\n[2/5] Création des sites...")
import xml.etree.ElementTree as _ET

_xml_path_sites = os.environ.get("SCRIBE_CONFIG_FILE") or (sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "config.xml"))
_SITES_XML = []
try:
    _root_xml = _ET.parse(_xml_path_sites).getroot()
    for _s in _root_xml.findall("sites/site"):
        _SITES_XML.append({
            "nom":             _s.findtext("nom", "Site").strip(),
            "code_finess":     None,  # NULL évite la contrainte UNIQUE
            "latitude":        float(_s.findtext("latitude", "46.0") or 46.0),
            "longitude":       float(_s.findtext("longitude", "6.3") or 6.3),
            "adresse":         (_s.findtext("adresse", "") or "").strip(),
            "telephone_garde": (_s.findtext("telephone_garde") or None),
        })
    print(f"      ✓ {len(_SITES_XML)} site(s) lus depuis {os.path.basename(_xml_path_sites)}")
except Exception as _e:
    print(f"      ⚠ Impossible de lire les sites depuis XML ({_e}) — sites par défaut")
    _SITES_XML = [
        {"nom": "Site Principal", "code_finess": None, "latitude": 46.03, "longitude": 6.32, "adresse": "", "telephone_garde": None},
        {"nom": "Site Secondaire", "code_finess": None, "latitude": 46.06, "longitude": 6.28, "adresse": "", "telephone_garde": None},
    ]

SITES = _SITES_XML

hospital_ids = {}
for s in SITES:
    h = Hospital(**s)
    db.add(h)
    db.flush()
    hospital_ids[s["nom"]] = h.id
    print(f"      [+] {s['nom']} ({s['latitude']:.4f},{s['longitude']:.4f})")

db.commit()
_site_list = list(hospital_ids.keys())
main_id = hospital_ids.get(_site_list[0], 1) if _site_list else 1
mds_id  = hospital_ids.get(_site_list[1], main_id) if len(_site_list) > 1 else main_id
ssr_id  = hospital_ids.get(_site_list[2], main_id) if len(_site_list) > 2 else main_id
cons_id = hospital_ids.get(_site_list[3], main_id) if len(_site_list) > 3 else main_id

# ── 3. UF (structure réelle, libellés génériques) ─────────────────────────
print("\n[3/5] Création des unités fonctionnelles...")

UFS = [
    # URGENCES
    ("URGENCES", "1001", "Urgences générales",           main_id),
    ("URGENCES", "1002", "Accueil / Orientation",        main_id),
    ("URGENCES", "1003", "SMUR antenne",                 main_id),
    ("URGENCES", "1004", "Urgences — maison de santé",   mds_id),

    # SOINS CRITIQUES
    ("SOINS CRITIQUES", "2001", "Réanimation",           main_id),
    ("SOINS CRITIQUES", "2002", "USC",                   main_id),
    ("SOINS CRITIQUES", "2003", "Soins intensifs",       main_id),

    # CHIRURGIE ANESTHESIE
    ("CHIRURGIE ANESTHESIE", "3001", "Bloc opératoire",          main_id),
    ("CHIRURGIE ANESTHESIE", "3002", "Chirurgie orthopédique",   main_id),
    ("CHIRURGIE ANESTHESIE", "3003", "Chirurgie viscérale",      main_id),
    ("CHIRURGIE ANESTHESIE", "3004", "Chirurgie ambulatoire",    main_id),
    ("CHIRURGIE ANESTHESIE", "3005", "Anesthésiologie",          main_id),
    ("CHIRURGIE ANESTHESIE", "3006", "SSPI",                     main_id),

    # MEDECINE
    ("MEDECINE", "4001", "Médecine générale",         main_id),
    ("MEDECINE", "4002", "Cardiologie",               main_id),
    ("MEDECINE", "4003", "Pneumologie",               main_id),
    ("MEDECINE", "4004", "Neurologie",                main_id),
    ("MEDECINE", "4005", "Médecine polyvalente",      main_id),
    ("MEDECINE", "4006", "Diabétologie",              main_id),
    ("MEDECINE", "4007", "Médecine ambulatoire",      cons_id),

    # CANCEROLOGIE
    ("CANCEROLOGIE", "5001", "Oncologie",                   main_id),
    ("CANCEROLOGIE", "5002", "Chimiothérapie ambulatoire",  main_id),
    ("CANCEROLOGIE", "5003", "Soins palliatifs",            main_id),

    # CARDIOVASCULAIRE
    ("CARDIOVASCULAIRE", "6001", "Cardiologie interventionnelle", main_id),
    ("CARDIOVASCULAIRE", "6002", "Explorations cardiaques",       main_id),
    ("CARDIOVASCULAIRE", "6003", "Chirurgie vasculaire",          main_id),

    # FME
    ("FME", "7001", "Maternité",             main_id),
    ("FME", "7002", "Néonatologie",          main_id),
    ("FME", "7003", "Pédiatrie",             main_id),
    ("FME", "7004", "Gynécologie",           main_id),

    # GERIATRIE
    ("GERIATRIE", "8001", "Court séjour gériatrique",   main_id),
    ("GERIATRIE", "8002", "SSR Gériatrique",            ssr_id),
    ("GERIATRIE", "8003", "USLD",                       ssr_id),
    ("GERIATRIE", "8004", "Évaluation gériatrique",     cons_id),

    # SANTE MENTALE
    ("SANTE MENTALE", "9001", "Psychiatrie adultes",    main_id),
    ("SANTE MENTALE", "9002", "Addictologie",           main_id),
    ("SANTE MENTALE", "9003", "CMP",                    cons_id),

    # MEDICO-TECHNIQUE ET REEDUCATION
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A001", "Imagerie / Scanner",     main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A002", "IRM",                    main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A003", "Laboratoire",            main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A004", "Kinésithérapie",         main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A005", "SSR orthopédique",       ssr_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A006", "SSR neurologique",       ssr_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A007", "Ergothérapie",           ssr_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A008", "Orthophonie",            ssr_id),

    # SANTE PUBLIQUE ET COMMUNAUTAIRE
    ("SANTE PUBLIQUE ET COMMUNAUTAIRE", "B001", "Hygiène hospitalière",   main_id),
    ("SANTE PUBLIQUE ET COMMUNAUTAIRE", "B002", "Santé au travail",       main_id),
    ("SANTE PUBLIQUE ET COMMUNAUTAIRE", "B003", "Coordination soins",     mds_id),
    ("SANTE PUBLIQUE ET COMMUNAUTAIRE", "B004", "Médecine préventive",    cons_id),

    # DNA
    ("DNA", "C001", "Coordination générale soins", main_id),

    # IFSI
    ("IFSI", "D001", "Formation infirmière",  main_id),

    # SUPPORT
    ("SUPPORT", "E001", "Direction Générale",              main_id),
    ("SUPPORT", "E002", "Direction Médicale",              main_id),
    ("SUPPORT", "E003", "DSI — Informatique",              main_id),
    ("SUPPORT", "E004", "Services Techniques",             main_id),
    ("SUPPORT", "E005", "Pharmacie",                       main_id),
    ("SUPPORT", "E006", "Stérilisation",                   main_id),
    ("SUPPORT", "E007", "Restauration / Hôtellerie",       main_id),
    ("SUPPORT", "E008", "Sécurité",                        main_id),
    ("SUPPORT", "E009", "RH / Paie",                       main_id),
    ("SUPPORT", "E010", "Qualité / Risques",               main_id),
    ("SUPPORT", "E011", "Achats",                          main_id),
    ("SUPPORT", "E012", "Pharmacie maison de santé",       mds_id),
    ("SUPPORT", "E013", "Accueil consultations",           cons_id),
]

for pole, code, libelle, hid in UFS:
    db.add(UniteFonctionnelle(code_uf=code, libelle=libelle, pole=pole, hospital_id=hid))

db.commit()
print(f"      ✓ {len(UFS)} UF créées")

# ── 4. UF transverses ──────────────────────────────────────────────────────
print("\n[4/5] UF transverses...")
transv = 0
for code, libelle, pole in [
    ("SECU-01","Sécurité physique","SECURITE PHYSIQUE"),
    ("LOGI-01","Logistique générale","LOGISTIQUE"),
    ("LOGI-02","Approvisionnement","LOGISTIQUE"),
    ("LOGI-03","Transport / Brancardage","LOGISTIQUE"),
]:
    for hid in hospital_ids.values():
        db.add(UniteFonctionnelle(code_uf=code, libelle=libelle, pole=pole, hospital_id=hid))
        transv += 1
db.commit()
print(f"      ✓ {transv} UF transverses")

# ── 5. Admin ───────────────────────────────────────────────────────────────
print("\n[5/5] Compte admin...")

login, password = "dircrise", "Scribe2026!"
# Lire les credentials depuis config.xml (pas config.js qui appartient à une autre instance)
_admin_xml = os.environ.get("SCRIBE_CONFIG_FILE") or (sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "config.xml"))
try:
    import xml.etree.ElementTree as _ET2
    _ar = _ET2.parse(_admin_xml).getroot()
    _adm = _ar.find("admin")
    if _adm is not None:
        login    = (_adm.findtext("login")    or login).strip()
        password = (_adm.findtext("password") or password).strip()
        print(f"      (credentials lus depuis {os.path.basename(_admin_xml)})")
except Exception:
    pass

if not db.query(User).filter_by(username=login).first():
    db.add(User(username=login, display_name="Directeur de Crise",
                role="admin", hashed_password=hashlib.sha256(password.encode()).hexdigest(),
                active=True))
    db.commit()
    print(f"      ✓ Admin : {login} / {password}")
else:
    print(f"      ~ Admin existant : {login}")

db.close()

# ── Générer config.js depuis config.xml ───────────────────────────────────
print("\n[+] Génération de config.js...")
import datetime, xml.etree.ElementTree as ET, json as _json

_xml_path = os.environ.get("SCRIBE_CONFIG_FILE") or (sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "config.xml"))
if os.path.exists(_xml_path):
    try:
        _root = ET.parse(_xml_path).getroot()
        _etab = _root.find("etablissement")
        _nom  = (_etab.findtext("nom") or "Établissement").strip() if _etab is not None else "Établissement"
        _sigl = (_etab.findtext("sigle") or "ETB").strip() if _etab is not None else "ETB"

        _dirs = []
        for d in _root.findall(".//directeurs/directeur"):
            n = (d.findtext("nom") or "").strip()
            f = (d.findtext("fonction") or "").strip()
            a = (d.findtext("abreviation") or "").strip()
            if n: _dirs.append({"nom": n, "fonction": f, "abreviation": a})

        _ann_n = []
        for c in _root.findall(".//annuaire_normal/contact"):
            _ann_n.append({"service": c.get("service",""), "local": c.get("local",""), "tel": c.get("tel","")})

        _ann_s = []
        for c in _root.findall(".//annuaire_secours/contact"):
            _ann_s.append({"service": c.get("service",""), "local": c.get("local",""),
                           "tel": c.get("tel",""), "note": c.get("note","")})

        _ia_el = _root.find("ia")
        _ia = {}
        if _ia_el is not None:
            _ia = {
                "fournisseur": (_ia_el.findtext("fournisseur") or "albert").strip(),
                "cle_api":     (_ia_el.findtext("cle_api")     or "").strip(),
                "modele":      (_ia_el.findtext("modele")      or "").strip(),
                "url_base":    (_ia_el.findtext("url_base")    or "").strip(),
            }

        _fed_el = _root.find("federation")
        _fed = {}
        if _fed_el is not None:
            _fed = {
                "enabled":            (_fed_el.findtext("enabled")            or "false").strip(),
                "collecteur_url":     (_fed_el.findtext("collecteur_url")     or "").strip(),
                "token":              (_fed_el.findtext("token")              or "").strip(),
                "intervalle_secondes":(_fed_el.findtext("intervalle_secondes") or "120").strip(),
                "share_details":      (_fed_el.findtext("share_details")      or "true").strip(),
                "share_min_urgency":  (_fed_el.findtext("share_min_urgency")  or "1").strip(),
            }

        _admin_el = _root.find("admin")
        _admin = {}
        if _admin_el is not None:
            _admin = {
                "login":    (_admin_el.findtext("login")    or "dircrise").strip(),
                "password": (_admin_el.findtext("password") or "Scribe2026!").strip(),
            }

        _cfg = {
            "etablissement":    {"nom": _nom, "sigle": _sigl},
            "login_tagline":    "",  # Texte mire de login — laisser vide = nom auto
            "admin":            _admin,
            "directeurs":       _dirs,
            "annuaire_normal":  _ann_n,
            "annuaire_secours": _ann_s,
            "ia":               _ia,
            "federation":       _fed,
            "exercice_mode":    os.environ.get("SCRIBE_EXERCICE_MODE", "0") == "1",
            "exercice_sigle":   os.environ.get("SCRIBE_EXO_SIGLE", ""),
        }

        _default_out = os.path.join(os.path.dirname(__file__), "app", "static", "config.js")
        _out = os.environ.get("SCRIBE_CONFIG_JS", _default_out)
        os.makedirs(os.path.dirname(_out), exist_ok=True)
        with open(_out, "w", encoding="utf-8") as _f:
            _f.write("// Généré par setup_demo — ne pas éditer manuellement\n")
            _f.write(f"// {_nom} | {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            _f.write("const SCRIBE_CONFIG = ")
            _f.write(_json.dumps(_cfg, ensure_ascii=False, indent=2))
            _f.write(";\n")

        print(f"      ✓ config.js généré : {len(_dirs)} directeur(s), IA={_ia.get('fournisseur','?')}, fédération={'activée' if _fed.get('enabled')=='true' else 'désactivée'}")
    except Exception as _e:
        print(f"      ⚠ config.js non généré : {_e} — lancez setup.py manuellement")
else:
    print("      ⚠ config.xml absent — config.js non généré. Créez config.xml d'abord.")

print("""
╔══════════════════════════════════════════════════════════════╗
║  DÉMO 2 — Clinique Saint-Benoît de Montrelay (CSBM)        ║
║  Initialisation terminée                                     ║
║                                                              ║
║  → python main.py   puis   http://localhost:8000            ║
╚══════════════════════════════════════════════════════════════╝
""")
