"""
setup_demo1.py — Initialisation DÉMO — Établissement 1
Centre Hospitalier de Valmont (CHV)
GPS : secteur nord du territoire (rayon ~30 km du centre)

Usage : python setup_demo1.py
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

# ── 2. Sites ───────────────────────────────────────────────────────────────
print("\n[2/5] Création des sites...")

SITES = [
    {
        "nom":             "Site Principal — Valmont",
        "code_finess":     "000000001",
        "latitude":        46.2012,
        "longitude":       6.1445,
        "adresse":         "1 avenue de l'Hôpital, 74000 Valmont",
        "telephone_garde": "04 50 00 00 01",
    },
    {
        "nom":             "Site Secondaire — Crestval",
        "code_finess":     "000000002",
        "latitude":        46.2480,
        "longitude":       6.0910,
        "adresse":         "12 route de la Clinique, 74100 Crestval",
        "telephone_garde": "04 50 00 00 02",
    },
    {
        "nom":             "Unité Psychiatrique — Les Pins",
        "code_finess":     "000000003",
        "latitude":        46.1850,
        "longitude":       6.1790,
        "adresse":         "Chemin des Pins, 74000 Valmont",
        "telephone_garde": None,
    },
    {
        "nom":             "EHPAD — Résidence du Lac",
        "code_finess":     "000000004",
        "latitude":        46.1620,
        "longitude":       6.2100,
        "adresse":         "15 allée du Lac, 74200 Rivebelle",
        "telephone_garde": None,
    },
    {
        "nom":             "SAMU — Centre 15",
        "code_finess":     "000000005",
        "latitude":        46.1950,
        "longitude":       6.1200,
        "adresse":         "Zone SDIS, 74000 Valmont",
        "telephone_garde": "15",
    },
]

# Mapping site principal pour import UF
hospital_ids = {}
for s in SITES:
    h = Hospital(**s)
    db.add(h)
    db.flush()
    hospital_ids[s["nom"]] = h.id
    print(f"      [+] {s['nom']}")

db.commit()
main_id  = hospital_ids["Site Principal — Valmont"]
sec_id   = hospital_ids["Site Secondaire — Crestval"]
psy_id   = hospital_ids["Unité Psychiatrique — Les Pins"]
ehpad_id = hospital_ids["EHPAD — Résidence du Lac"]
samu_id  = hospital_ids["SAMU — Centre 15"]

# ── 3. UF (structure réelle, libellés génériques) ─────────────────────────
print("\n[3/5] Création des unités fonctionnelles...")

UFS = [
    # URGENCES
    ("URGENCES", "1001", "Urgences adultes",            main_id),
    ("URGENCES", "1002", "SMUR",                        main_id),
    ("URGENCES", "1003", "UHCD",                        main_id),
    ("URGENCES", "1004", "Urgences pédiatriques",       main_id),
    ("URGENCES", "1005", "Accueil / Triage",            main_id),
    ("URGENCES", "1101", "Urgences — site secondaire",  sec_id),

    # SOINS CRITIQUES
    ("SOINS CRITIQUES", "2001", "Réanimation polyvalente",   main_id),
    ("SOINS CRITIQUES", "2002", "USC",                       main_id),
    ("SOINS CRITIQUES", "2003", "USIC",                      main_id),
    ("SOINS CRITIQUES", "2004", "Soins intensifs digestifs", main_id),
    ("SOINS CRITIQUES", "2005", "Néonatologie intensive",    main_id),
    ("SOINS CRITIQUES", "2006", "Réa pédiatrique",          main_id),

    # CHIRURGIE ANESTHESIE
    ("CHIRURGIE ANESTHESIE", "3001", "Bloc opératoire central",     main_id),
    ("CHIRURGIE ANESTHESIE", "3002", "Chirurgie viscérale",         main_id),
    ("CHIRURGIE ANESTHESIE", "3003", "Chirurgie orthopédique",      main_id),
    ("CHIRURGIE ANESTHESIE", "3004", "Chirurgie ambulatoire",       main_id),
    ("CHIRURGIE ANESTHESIE", "3005", "Neurochirurgie",              main_id),
    ("CHIRURGIE ANESTHESIE", "3006", "Chirurgie thoracique",        main_id),
    ("CHIRURGIE ANESTHESIE", "3007", "Anesthésiologie",             main_id),
    ("CHIRURGIE ANESTHESIE", "3008", "SSPI",                        main_id),
    ("CHIRURGIE ANESTHESIE", "3101", "Bloc secondaire",             sec_id),
    ("CHIRURGIE ANESTHESIE", "3102", "Chirurgie ambulatoire sec.",  sec_id),

    # MEDECINE
    ("MEDECINE", "4001", "Médecine interne",          main_id),
    ("MEDECINE", "4002", "Cardiologie",               main_id),
    ("MEDECINE", "4003", "Pneumologie",               main_id),
    ("MEDECINE", "4004", "Neurologie",                main_id),
    ("MEDECINE", "4005", "Infectiologie",             main_id),
    ("MEDECINE", "4006", "Gastroentérologie",         main_id),
    ("MEDECINE", "4007", "Endocrinologie",            main_id),
    ("MEDECINE", "4008", "Rhumatologie",              main_id),
    ("MEDECINE", "4009", "Dermatologie",              main_id),
    ("MEDECINE", "4010", "Hématologie",               main_id),
    ("MEDECINE", "4011", "Médecine polyvalente",      sec_id),
    ("MEDECINE", "4012", "Gériatrie aiguë",           sec_id),

    # CANCEROLOGIE
    ("CANCEROLOGIE", "5001", "Oncologie médicale",         main_id),
    ("CANCEROLOGIE", "5002", "Hématologie / Oncologie",    main_id),
    ("CANCEROLOGIE", "5003", "Radiothérapie",              main_id),
    ("CANCEROLOGIE", "5004", "Chimiothérapie ambulatoire", main_id),
    ("CANCEROLOGIE", "5005", "HDJ Oncologie",              main_id),

    # CARDIOVASCULAIRE
    ("CARDIOVASCULAIRE", "6001", "Cardiologie interventionnelle", main_id),
    ("CARDIOVASCULAIRE", "6002", "Chirurgie cardiaque",          main_id),
    ("CARDIOVASCULAIRE", "6003", "Rythmologie",                  main_id),
    ("CARDIOVASCULAIRE", "6004", "Explorations vasculaires",     main_id),

    # FME (Femme Mère Enfant)
    ("FME", "7001", "Maternité — Gynécologie",   main_id),
    ("FME", "7002", "Néonatologie",              main_id),
    ("FME", "7003", "Pédiatrie",                 main_id),
    ("FME", "7004", "Médecine néonatale",        main_id),
    ("FME", "7005", "Obstétrique",               main_id),
    ("FME", "7006", "Maternité secondaire",      sec_id),

    # GERIATRIE
    ("GERIATRIE", "8001", "Court séjour gériatrique",   main_id),
    ("GERIATRIE", "8002", "SSR Gériatrique",            main_id),
    ("GERIATRIE", "8003", "USLD",                       main_id),
    ("GERIATRIE", "8004", "Consultation mémoire",       main_id),
    ("GERIATRIE", "8005", "Gérontopsychiatrie",         sec_id),

    # SANTE MENTALE
    ("SANTE MENTALE", "9001", "Psychiatrie adultes",        hospital_ids["Unité Psychiatrique — Les Pins"]),
    ("SANTE MENTALE", "9002", "Psychiatrie infanto-juvénile", hospital_ids["Unité Psychiatrique — Les Pins"]),
    ("SANTE MENTALE", "9003", "Addictologie",               hospital_ids["Unité Psychiatrique — Les Pins"]),
    ("SANTE MENTALE", "9004", "CMP adultes",                hospital_ids["Unité Psychiatrique — Les Pins"]),
    ("SANTE MENTALE", "9005", "HDJ Psychiatrie",            hospital_ids["Unité Psychiatrique — Les Pins"]),

    # MEDICO-TECHNIQUE ET REEDUCATION
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A001", "Imagerie / Scanner",         main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A002", "IRM",                        main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A003", "Laboratoire biologie",       main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A004", "Anatomie pathologique",      main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A005", "Kinésithérapie",             main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A006", "Ergothérapie",               main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A007", "Orthophonie",                main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A008", "Neuropsychologie",           main_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A009", "SSR neurologique",           sec_id),
    ("MEDICO-TECHNIQUE ET REEDUCATION", "A010", "SSR cardiologique",          sec_id),

    # SANTE PUBLIQUE ET COMMUNAUTAIRE
    ("SANTE PUBLIQUE ET COMMUNAUTAIRE", "B001", "Hygiène hospitalière",          main_id),
    ("SANTE PUBLIQUE ET COMMUNAUTAIRE", "B002", "Santé au travail",              main_id),
    ("SANTE PUBLIQUE ET COMMUNAUTAIRE", "B003", "Médecine préventive",           main_id),
    ("SANTE PUBLIQUE ET COMMUNAUTAIRE", "B004", "Consultation voyage / vaccins", main_id),

    # DNA (Direction Nursing / Activité)
    ("DNA", "C001", "Coordination générale des soins", main_id),

    # IFSI
    ("IFSI", "D001", "IFSI — Institut de formation",  main_id),
    ("IFSI", "D002", "Formation continue",             main_id),

    # SUPPORT
    ("SUPPORT", "E001", "Direction Générale",           main_id),
    ("SUPPORT", "E002", "Direction des Soins",          main_id),
    ("SUPPORT", "E003", "DSI — Informatique",           main_id),
    ("SUPPORT", "E004", "Services Techniques",          main_id),
    ("SUPPORT", "E005", "Pharmacie",                    main_id),
    ("SUPPORT", "E006", "Stérilisation",                main_id),
    ("SUPPORT", "E007", "Restauration",                 main_id),
    ("SUPPORT", "E008", "Blanchisserie",                main_id),
    ("SUPPORT", "E009", "Sécurité / Gardiennage",       main_id),
    ("SUPPORT", "E010", "DRH",                          main_id),
    ("SUPPORT", "E011", "Finances / Contrôle de gestion", main_id),
    ("SUPPORT", "E012", "Achats / Logistique",          main_id),
    ("SUPPORT", "E013", "Qualité / Gestion des risques",main_id),
    ("SUPPORT", "E101", "DSI secondaire",               sec_id),
    ("SUPPORT", "E102", "Pharmacie secondaire",         sec_id),

    # UNITÉ PSYCHIATRIQUE — Les Pins
    ("SANTE MENTALE", "P001", "Hospitalisation adultes",        psy_id),
    ("SANTE MENTALE", "P002", "Hospitalisation adolescents",    psy_id),
    ("SANTE MENTALE", "P003", "Psychiatrie de liaison",         psy_id),
    ("SANTE MENTALE", "P004", "Urgences psychiatriques",        psy_id),
    ("SANTE MENTALE", "P005", "Réhabilitation psychosociale",   psy_id),
    ("SUPPORT",       "P101", "Administration — Les Pins",      psy_id),

    # EHPAD — Résidence du Lac
    ("GERIATRIE",     "G001", "EHPAD — Unité A",                ehpad_id),
    ("GERIATRIE",     "G002", "EHPAD — Unité B",                ehpad_id),
    ("GERIATRIE",     "G003", "Unité Alzheimer",                ehpad_id),
    ("GERIATRIE",     "G004", "Soins de suite gériatriques",    ehpad_id),
    ("SUPPORT",       "G101", "Administration EHPAD",           ehpad_id),

    # SAMU — Centre 15
    ("URGENCES",      "S001", "Régulation médicale",            samu_id),
    ("URGENCES",      "S002", "SMUR Valmont",                   samu_id),
    ("URGENCES",      "S003", "SMUR secondaire",                samu_id),
    ("SUPPORT",       "S101", "Administration SAMU",            samu_id),
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
config_js = os.path.join(os.path.dirname(__file__), "app", "static", "config.js")
if os.path.exists(config_js):
    try:
        raw = open(config_js, encoding="utf-8").read()
        start = raw.find("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
        cfg = json.loads(raw[start:raw.rfind(";")])
        login    = cfg.get("admin", {}).get("login", login)
        password = cfg.get("admin", {}).get("password", password)
        print("      (credentials lus depuis config.js)")
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

_xml_path = os.path.join(os.path.dirname(__file__), "config.xml")
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
        }

        _out = os.path.join(os.path.dirname(__file__), "app", "static", "config.js")
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
║  DÉMO 1 — Centre Hospitalier de Valmont (CHV)               ║
║  Initialisation terminée                                     ║
║                                                              ║
║  → python main.py   puis   http://localhost:8000            ║
╚══════════════════════════════════════════════════════════════╝
""")
