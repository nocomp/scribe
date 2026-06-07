"""
setup_capacite_default.py — Charge le référentiel capacitaire générique
dans la base SCRIBE pour toute nouvelle instance créée via le wizard.

Référentiel basé sur uf_modele.xlsx : 37 UF réparties sur 9 pôles
(Urgences, Soins critiques, Chirurgie, Médecine, Maternité-Pédiatrie,
Gériatrie, Imagerie/Biologie, Pharmacie, Direction-Support).

Sites : Hôpital 1 (principal) et Hôpital 2 (secondaire). Les UF "BI SITE"
sont dupliquées sur les deux. L'utilisateur peut renommer ces sites via
l'interface ADMIN UF pour les adapter à son organisation réelle.

Les téléphones sont vides : à renseigner par l'administrateur SCRIBE.

Lancer : python setup_capacite_default.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models import CapaciteReferentiel

UNITES = [
    # (service_nom, uf_code, pole, site, capacite_totale, tension_1, tension_2,
    #  accept_H, accept_F, accept_I, telephone_cadre, ordre)

    # ── REA/URGENCES ──
    ('Urgences Adultes'                 , '1001'  , 'REA/URGENCES' , 'Hôpital 1' ,  12, 0, 0, True , True , True , "", 1),
    ('Uhcd'                             , '1002'  , 'REA/URGENCES' , 'Hôpital 1' ,  12, 0, 0, True , True , True , "", 2),
    ('Smur'                             , '1003'  , 'REA/URGENCES' , 'Hôpital 1' ,  12, 0, 0, True , True , True , "", 3),
    ('Urgences Pediatriques'            , '1004'  , 'REA/URGENCES' , 'Hôpital 1' ,  12, 0, 0, True , True , True , "", 4),
    ('Reanimation Adultes'              , '2001'  , 'REA/URGENCES' , 'Hôpital 1' ,  14, 0, 0, True , True , True , "", 5),
    ('Soins Continus'                   , '2002'  , 'REA/URGENCES' , 'Hôpital 1' ,  14, 0, 0, True , True , True , "", 6),
    ('Usic'                             , '2003'  , 'REA/URGENCES' , 'Hôpital 1' ,  14, 0, 0, True , True , True , "", 7),
    # ── CHIRURGIE ──
    ('Bloc Operatoire Central'          , '3001'  , 'CHIRURGIE'    , 'Hôpital 1' ,  22, 0, 0, True , True , True , "", 8),
    ('Chirurgie Viscerale'              , '3002'  , 'CHIRURGIE'    , 'Hôpital 1' ,  22, 0, 0, True , True , True , "", 9),
    ('Chirurgie Orthopedique'           , '3003'  , 'CHIRURGIE'    , 'Hôpital 1' ,  22, 0, 0, True , True , True , "", 10),
    ('Chirurgie Ambulatoire'            , '3004'  , 'CHIRURGIE'    , 'Hôpital 1' ,  22, 0, 0, True , True , True , "", 11),
    # ── MÉDECINE ──
    ('Medecine Interne'                 , '4001'  , 'MÉDECINE'     , 'Hôpital 1' ,  24, 0, 0, True , True , True , "", 12),
    ('Cardiologie'                      , '4002'  , 'MÉDECINE'     , 'Hôpital 1' ,  24, 0, 0, True , True , True , "", 13),
    ('Pneumologie'                      , '4003'  , 'MÉDECINE'     , 'Hôpital 1' ,  24, 0, 0, True , True , True , "", 14),
    ('Neurologie'                       , '4004'  , 'MÉDECINE'     , 'Hôpital 1' ,  24, 0, 0, True , True , True , "", 15),
    ('Gastro-Enterologie'               , '4005'  , 'MÉDECINE'     , 'Hôpital 1' ,  24, 0, 0, True , True , True , "", 16),
    ('Infectiologie'                    , '4006'  , 'MÉDECINE'     , 'Hôpital 1' ,  24, 0, 0, True , True , True , "", 17),
    ('Nephrologie / Hemodialyse'        , '4007'  , 'MÉDECINE'     , 'Hôpital 1' ,  24, 0, 0, True , True , True , "", 18),
    # ── FME ──
    ('Maternite / Gynecologie'          , '5001'  , 'FME'          , 'Hôpital 1' ,  18, 0, 0, True , True , False, "", 19),
    ('Bloc Accouchement'                , '5002'  , 'FME'          , 'Hôpital 1' ,  18, 0, 0, True , True , False, "", 20),
    ('Neonatologie'                     , '5003'  , 'FME'          , 'Hôpital 1' ,  18, 0, 0, True , True , False, "", 21),
    ('Pediatrie Generale'               , '5004'  , 'FME'          , 'Hôpital 1' ,  18, 0, 0, True , True , False, "", 22),
    # ── LONG SÉJOUR ──
    ('Court Sejour Geriatrique'         , '6001'  , 'LONG SÉJOUR'  , 'Hôpital 1' ,  25, 0, 0, True , True , True , "", 23),
    ('Ssr Geriatrique'                  , '6002'  , 'LONG SÉJOUR'  , 'Hôpital 1' ,  25, 0, 0, True , True , True , "", 24),
    ('Ehpad'                            , '6003'  , 'LONG SÉJOUR'  , 'Hôpital 2' ,  25, 0, 0, True , True , True , "", 25),
    # ── SUPPORT ──
    ('Radiologie / Scanner'             , '7001'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 26),
    ('Radiologie / Scanner'             , '7001'  , 'SUPPORT'      , 'Hôpital 2' ,   0, 0, 0, True , True , True , "", 27),
    ('Irm'                              , '7002'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 28),
    ('Laboratoire Biochimie'            , '7003'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 29),
    ('Laboratoire Biochimie'            , '7003'  , 'SUPPORT'      , 'Hôpital 2' ,   0, 0, 0, True , True , True , "", 30),
    ('Laboratoire Microbiologie'        , '7004'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 31),
    ('Laboratoire Microbiologie'        , '7004'  , 'SUPPORT'      , 'Hôpital 2' ,   0, 0, 0, True , True , True , "", 32),
    ('Pharmacie'                        , '8001'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 33),
    ('Pharmacie'                        , '8001'  , 'SUPPORT'      , 'Hôpital 2' ,   0, 0, 0, True , True , True , "", 34),
    ('Sterilisation Centrale'           , '8002'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 35),
    # ── MÉDECINE ──
    ('Medecine Polyvalente'             , '9001'  , 'MÉDECINE'     , 'Hôpital 2' ,  24, 0, 0, True , True , True , "", 36),
    # ── CHIRURGIE ──
    ('Bloc Operatoire Secondaire'       , '9002'  , 'CHIRURGIE'    , 'Hôpital 2' ,  22, 0, 0, True , True , True , "", 37),
    # ── REA/URGENCES ──
    ('Urgences Site Secondaire'         , '9003'  , 'REA/URGENCES' , 'Hôpital 2' ,  12, 0, 0, True , True , True , "", 38),
    # ── SUPPORT ──
    ('Direction Generale'               , '9901'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 39),
    ('Dsi Informatique'                 , '9902'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 40),
    ('Services Techniques'              , '9903'  , 'SUPPORT'      , 'Hôpital 1' ,   0, 0, 0, True , True , True , "", 41),
]

def run():
    db = SessionLocal()
    try:
        existants = {r.service_nom for r in db.query(CapaciteReferentiel).all()}
        nb_crees = 0
        for row in UNITES:
            nom = row[0]
            if nom in existants:
                continue
            ref = CapaciteReferentiel(
                service_nom=nom, uf_code=row[1], pole=row[2],
                site=row[3], capacite_totale=row[4],
                tension_1=row[5], tension_2=row[6],
                accept_homme=row[7], accept_femme=row[8],
                accept_indiffer=row[9], telephone_cadre=row[10],
                ordre_affichage=row[11],
            )
            db.add(ref)
            nb_crees += 1
        db.commit()
        print(f"  ✓ {nb_crees} unités créées ({len(existants)} existantes ignorées)")
        print(f"  ✓ Total référentiel : {db.query(CapaciteReferentiel).count()} unités")
    finally:
        db.close()

if __name__ == "__main__":
    run()
