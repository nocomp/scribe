"""
seed.py — Initialisation des sites de votre établissement.
Usage : python seed.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
import app.models  # noqa
from app.models import Hospital

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    hospitals = [
        {
            "nom": "Site Principal",
            "code_finess": "740000001",
            "latitude": 45.9336015,
            "longitude": 6.1145528,
            "adresse": "1 avenue de l'Hôpital, Epagny-Metz-Tessy",
            "telephone_garde": None
        },
        {
            "nom": "Site Secondaire",
            "code_finess": "740000002",
            "latitude": 46.1467717,
            "longitude": 6.0772328,
            "adresse": "2 avenue de la Santé, 00000 Ville",
            "telephone_garde": None
        },
        {
            "nom": "Site Psychiatrie",
            "code_finess": "740000003",
            "latitude": 45.9292121,
            "longitude": 6.112887,
            "adresse": "149 route des Sarves, Epagny-Metz-Tessy",
            "telephone_garde": None
        },
        {
            "nom": "EHPAD – Résidence",
            "code_finess": "740000004",
            "latitude": 45.8923831,
            "longitude": 6.1043548,
            "adresse": "21 rue du Bois Gentil, Seynod",
            "telephone_garde": None
        },
        {
            "nom": "Centre 15 – SAMU",
            "code_finess": "740000005",
            "latitude": 46.2180266,
            "longitude": 6.0854763,
            "adresse": "Locaux SDIS, Meythet",
            "telephone_garde": None
        },
        {
            "nom": "Blanchisserie",
            "code_finess": "740000006",
            "latitude": 45.91326,
            "longitude": 6.0991175,
            "adresse": "10 av. du Pont de Tasset, Meythet",
            "telephone_garde": None
        },
        {
            "nom": "Site Formation",
            "code_finess": "740000007",
            "latitude": 45.938598,
            "longitude": 6.1181999,
            "adresse": "Impasse de la Ravoire, Epagny-Metz-Tessy",
            "telephone_garde": None
        },
    ]

    for h_data in hospitals:
        existing = db.query(Hospital).filter(Hospital.nom == h_data["nom"]).first()
        if not existing:
            db.add(Hospital(**h_data))
            print(f"  [+] Ajouté : {h_data['nom']}")
        else:
            existing.latitude  = h_data["latitude"]
            existing.longitude = h_data["longitude"]
            existing.adresse   = h_data["adresse"]
            print(f"  [~] Mis à jour : {h_data['nom']}")

    db.commit()

    # ── UF virtuelles transverses (Sécurité physique / Logistique) ────────────
    from app.models import UniteFonctionnelle
    UF_TRANSVERSES = [
        {"code_uf": "SECU-01", "libelle": "Sécurité physique",      "pole": "SECURITE PHYSIQUE"},
        {"code_uf": "LOGI-01", "libelle": "Logistique générale",    "pole": "LOGISTIQUE"},
        {"code_uf": "LOGI-02", "libelle": "Approvisionnement",      "pole": "LOGISTIQUE"},
        {"code_uf": "LOGI-03", "libelle": "Transport / Brancardage","pole": "LOGISTIQUE"},
    ]
    all_hospitals = db.query(Hospital).all()
    uf_added = 0
    for h in all_hospitals:
        for uf_data in UF_TRANSVERSES:
            exists = db.query(UniteFonctionnelle).filter_by(
                code_uf=uf_data["code_uf"], hospital_id=h.id
            ).first()
            if not exists:
                db.add(UniteFonctionnelle(
                    code_uf=uf_data["code_uf"],
                    libelle=uf_data["libelle"],
                    pole=uf_data["pole"],
                    hospital_id=h.id,
                ))
                uf_added += 1
    db.commit()
    if uf_added:
        print(f"  [+] {uf_added} UF transverses ajoutées (sécurité physique / logistique)")

    db.close()
    print("\n[✓] Seed terminé. Lance : python main.py")

if __name__ == "__main__":
    seed()
