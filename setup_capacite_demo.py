"""
setup_capacite_demo.py — Référentiel capacitaire pour la démo CHV Valmont
Compatible avec setup_demo1.py (5 sites, 126 UF)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.database import SessionLocal, Base, engine
from app.models import CapaciteReferentiel

Base.metadata.create_all(bind=engine)
db = SessionLocal()

VALMONT  = "Valmont"
CRESTVAL = "Crestval"
LES_PINS = "Les Pins"
EHPAD    = "Ehpad du Lac"

UNITES = [
    # (pole, service_nom, uf_code, site, capa, tension1, tension2, H, F, I)
    ("URGENCES",             "Urgences adultes",            "1001", VALMONT,  24, 18, 22, False, False, True),
    ("URGENCES",             "UHCD",                        "1003", VALMONT,  12,  9, 11, False, False, True),
    ("URGENCES",             "Urgences pediatriques",       "1004", VALMONT,  10,  8,  9, False, False, True),
    ("SOINS CRITIQUES",      "Reanimation polyvalente",     "7900", VALMONT,  16, 12, 15, False, False, True),
    ("SOINS CRITIQUES",      "Soins continus",              "7920", VALMONT,  10,  8,  9, False, False, True),
    ("CHIRURGIE ANESTHESIE", "Chirurgie viscerale",         "6100", VALMONT,  28, 22, 26, True,  True,  False),
    ("CHIRURGIE ANESTHESIE", "Orthopedie Traumatologie",    "6200", VALMONT,  32, 25, 30, True,  True,  False),
    ("CHIRURGIE ANESTHESIE", "Neurochirurgie",              "6400", VALMONT,  20, 15, 18, False, False, True),
    ("CHIRURGIE ANESTHESIE", "Bloc operatoire central",     "6500", VALMONT,   0,  0,  0, False, False, True),
    ("MEDECINE",             "Medecine interne A",          "2100", VALMONT,  28, 22, 26, True,  True,  False),
    ("MEDECINE",             "Neurologie",                  "2200", VALMONT,  24, 18, 22, True,  True,  False),
    ("MEDECINE",             "Pneumologie",                 "2300", VALMONT,  24, 18, 22, True,  True,  False),
    ("MEDECINE",             "Hepato-gastroenterologie",    "2400", VALMONT,  20, 15, 18, True,  True,  False),
    ("MEDECINE",             "Infectiologie",               "2500", VALMONT,  18, 14, 17, True,  True,  False),
    ("CARDIOVASCULAIRE",     "Cardiologie",                 "3100", VALMONT,  28, 22, 26, True,  True,  False),
    ("CARDIOVASCULAIRE",     "USIC",                        "3200", VALMONT,   8,  6,  7, False, False, True),
    ("FME",                  "Maternite",                   "4100", VALMONT,  30, 24, 28, False, True,  False),
    ("FME",                  "Gynecologie",                 "4200", VALMONT,  16, 12, 15, False, True,  False),
    ("FME",                  "Neonatologie",                "4300", VALMONT,  12,  9, 11, False, False, True),
    ("FME",                  "Pediatrie",                   "4400", VALMONT,  20, 15, 18, False, False, True),
    ("CANCEROLOGIE",         "Oncologie medicale",          "5100", VALMONT,  24, 18, 22, True,  True,  False),
    ("CANCEROLOGIE",         "HDJ Chimiotherapie",          "5200", VALMONT,  16, 12, 15, False, False, True),
    ("GERIATRIE",            "Geriatrie court sejour",      "8100", VALMONT,  28, 22, 26, True,  True,  False),
    ("GERIATRIE",            "Soins palliatifs",            "8200", VALMONT,  12,  9, 11, False, False, True),
    ("SANTE MENTALE",        "Psychiatrie adulte",          "9100", LES_PINS, 30, 24, 28, True,  True,  False),
    ("SANTE MENTALE",        "Psychiatrie urgences",        "9200", LES_PINS,  8,  6,  7, False, False, True),
    ("MEDECINE",             "Medecine polyvalente Crestval","C100", CRESTVAL, 24, 18, 22, True,  True,  False),
    ("CHIRURGIE ANESTHESIE", "Chir ambulatoire Crestval",   "C200", CRESTVAL, 20, 15, 18, True,  True,  False),
    ("GERIATRIE",            "SSR Geriatrie Crestval",      "C300", CRESTVAL, 30, 24, 28, True,  True,  False),
    ("GERIATRIE",            "EHPAD Residence du Lac",      "E100", EHPAD,    80, 70, 78, True,  True,  False),
    ("GERIATRIE",            "USLD Lac",                    "E200", EHPAD,    30, 25, 28, True,  True,  False),
]

created = skipped = 0
for pole, nom, code, site, capa, t1, t2, h, f, ind in UNITES:
    exists = db.query(CapaciteReferentiel).filter_by(
        uf_code=code, site=site
    ).first()
    if exists:
        skipped += 1
        continue
    db.add(CapaciteReferentiel(
        service_nom=nom, uf_code=code, pole=pole, site=site,
        capacite_totale=capa, tension_1=t1, tension_2=t2,
        accept_homme=h, accept_femme=f, accept_indiffer=ind,
    ))
    created += 1

db.commit()
total = db.query(CapaciteReferentiel).count()
print(f"  \u2713 {created} unites creees ({skipped} existantes ignorees)")
print(f"  \u2713 Total referentiel : {total} unites (CHV Valmont demo)")
db.close()
