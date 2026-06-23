"""
seed_uf_demo.py — Unités Fonctionnelles démo pour tous les sites Arc Alpin
Crée des UF réalistes par pôle pour chaque site enregistré en DB.
Pour CHAG : synchronise aussi depuis CapaciteReferentiel (données BedManager réelles).
Usage: python3 seed_uf_demo.py
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UF_PAR_POLE = {
    "Urgences & SAMU": [
        "Urgences adultes", "Urgences pédiatriques", "SAMU / Centre 15",
        "SMUR primaire", "Zone d'attente", "Déchocage",
    ],
    "Médecine": [
        "Médecine interne", "Cardiologie", "Pneumologie",
        "Neurologie", "Gastro-entérologie", "Médecine polyvalente",
    ],
    "Chirurgie": [
        "Chirurgie viscérale", "Orthopédie-Traumatologie",
        "Chirurgie ambulatoire", "Bloc opératoire", "SSPI",
    ],
    "Réanimation & Soins critiques": [
        "Réanimation adultes", "Soins continus", "USC",
        "Surveillance continue cardiologique",
    ],
    "Maternité & Pédiatrie": [
        "Maternité", "Salle de naissance", "Pédiatrie", "Gynécologie",
    ],
    "Plateau technique": [
        "Imagerie médicale", "Scanner", "IRM", "Laboratoire", "Pharmacie",
    ],
    "Logistique & Support": [
        "Direction", "DRH", "DAF", "DSI", "Services techniques", "Sécurité",
    ],
}

POLES_PRINCIPAL  = list(UF_PAR_POLE.keys())
POLES_SECONDAIRE = ["Urgences & SAMU", "Médecine", "Chirurgie",
                    "Plateau technique", "Logistique & Support"]


def seed_for_db_direct(db_path: str, label: str):
    """Seed UF directement via sqlite3 — pas de dépendance à SQLAlchemy engine cache."""
    if not os.path.exists(db_path):
        print(f"  {label}: DB absente — skip")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # S'assurer que la table existe
    c.execute("""
        CREATE TABLE IF NOT EXISTS unites_fonctionnelles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id INTEGER NOT NULL,
            code_uf TEXT,
            libelle TEXT NOT NULL,
            pole TEXT,
            actif INTEGER DEFAULT 1
        )
    """)

    # Récupérer les sites
    sites = c.execute("SELECT id, nom FROM hospitals ORDER BY id").fetchall()
    if not sites:
        print(f"  {label}: aucun site en DB")
        conn.close()
        return

    created = 0

    # Pour CHAG : synchroniser depuis capacite_referentiel si disponible
    try:
        cap_refs = c.execute(
            "SELECT DISTINCT service_nom, pole, site FROM capacite_referentiel"
        ).fetchall()
        if cap_refs:
            # Trouver l'hôpital principal (id le plus petit)
            main_site_id = sites[0][0]
            for service_nom, pole, site_cap in cap_refs:
                if not service_nom:
                    continue
                # Trouver l'hospital_id correspondant au site
                h_id = main_site_id
                for sid, snom in sites:
                    if site_cap and site_cap.lower() in snom.lower():
                        h_id = sid
                        break
                exists = c.execute(
                    "SELECT id FROM unites_fonctionnelles WHERE hospital_id=? AND libelle=?",
                    (h_id, service_nom)
                ).fetchone()
                if not exists:
                    code = f"CAP{h_id:02d}{created+1:03d}"
                    c.execute(
                        "INSERT INTO unites_fonctionnelles (hospital_id, code_uf, libelle, pole, actif) VALUES (?,?,?,?,1)",
                        (h_id, code, service_nom, pole or "Médecine")
                    )
                    created += 1
            print(f"  {label}: {created} UF depuis CapaciteReferentiel")
            created_cap = created
            created = 0
    except Exception as e:
        cap_refs = []

    # Pour tous les sites : UF génériques par pôle
    for idx, (h_id, h_nom) in enumerate(sites):
        poles = POLES_PRINCIPAL if idx == 0 else POLES_SECONDAIRE
        for pole in poles:
            for uf_libelle in UF_PAR_POLE[pole]:
                exists = c.execute(
                    "SELECT id FROM unites_fonctionnelles WHERE hospital_id=? AND libelle=?",
                    (h_id, uf_libelle)
                ).fetchone()
                if not exists:
                    total_uf = c.execute(
                        "SELECT COUNT(*) FROM unites_fonctionnelles WHERE hospital_id=?", (h_id,)
                    ).fetchone()[0]
                    code = f"UF{h_id:02d}{total_uf+1:03d}"
                    c.execute(
                        "INSERT INTO unites_fonctionnelles (hospital_id, code_uf, libelle, pole, actif) VALUES (?,?,?,?,1)",
                        (h_id, code, uf_libelle, pole)
                    )
                    created += 1

    conn.commit()
    total = c.execute("SELECT COUNT(*) FROM unites_fonctionnelles").fetchone()[0]
    print(f"  {label}: {created} UF génériques créées — total {total} UF / {len(sites)} site(s)")
    conn.close()


BASE = os.path.dirname(os.path.abspath(__file__))
instances = [
    (os.path.join(BASE, "scribe_chag.db"),  "CHAG"),
    (os.path.join(BASE, "scribe_ght2.db"),  "GHTLMB"),
    (os.path.join(BASE, "scribe_ght3.db"),  "GHTSAV"),
    (os.path.join(BASE, "scribe_ght4.db"),  "GHTAD38"),
]

# Si DATABASE_URL est défini (lancement depuis subshell instance), n'opérer que sur cette DB
db_url_env = os.environ.get("DATABASE_URL", "")
if db_url_env and db_url_env.startswith("sqlite:///"):
    single_db = db_url_env.replace("sqlite:///", "", 1)
    label = os.path.basename(single_db).replace(".db", "").upper()
    print(f"Seed UF — {label}")
    print("=" * 50)
    try:
        seed_for_db_direct(single_db, label)
    except Exception as e:
        print(f"  {label}: ERREUR {e}")
    print("=" * 50)
else:
    print("Seed UF démo — Arc Alpin")
    print("=" * 50)
    for db_path, label in instances:
        try:
            seed_for_db_direct(db_path, label)
        except Exception as e:
            print(f"  {label}: ERREUR {e}")
    print("=" * 50)
