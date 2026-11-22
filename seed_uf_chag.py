"""
seed_uf_chag.py — Injecte les UF strictement conformes au référentiel CHV 2026.
Source: uf_chag_reference.json (extrait du fichier officiel FICHIER UF 2026).
- ANNECY : site hospitalier principal Valmont (et sites dont le nom contient ANNECY)
- ST JULIEN : Hôpital Saint-Julien (et sites dont le nom contient JULIEN)
- Autres sites CHV (Psychiatrie, Plainville, etc.) : pas d'UF référentielles
- Pour les GHTs démo : 5 UF représentatives par pôle CHV

Usage: python3 seed_uf_chag.py [DB_PATH]
"""
import os, sys, sqlite3, json
from pathlib import Path

BASE = Path(__file__).parent
JSON_PATH = BASE / 'uf_chag_reference.json'


def seed_chag_ufs(db_path: str, label: str = "CHV"):
    if not Path(db_path).exists():
        print(f"  {label}: DB absente — skip")
        return
    if not JSON_PATH.exists():
        print(f"  {label}: uf_chag_reference.json absent — skip")
        return

    with open(JSON_PATH, encoding='utf-8') as f:
        uf_data = json.load(f)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS unites_fonctionnelles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER NOT NULL,
        code_uf TEXT, libelle TEXT NOT NULL, pole TEXT
    )""")

    sites = c.execute("SELECT id, nom FROM hospitals ORDER BY id").fetchall()
    if not sites:
        print(f"  {label}: aucun site en DB"); conn.close(); return

    # Mapper chaque site DB vers ANNECY ou ST JULIEN selon le nom
    # Tous les autres sites ne reçoivent pas d'UF référentielles
    annecy_ids = []
    stjulien_ids = []
    for h_id, h_nom in sites:
        nom_up = h_nom.upper()
        if 'ANNECY' in nom_up or ('PRINCIPAL' in nom_up and 'ST JULIEN' not in nom_up):
            annecy_ids.append(h_id)
        elif 'JULIEN' in nom_up or 'ST-JULIEN' in nom_up or 'SAINT-JULIEN' in nom_up:
            stjulien_ids.append(h_id)

    # Vider les UF existantes pour les sites couverts
    all_covered_ids = annecy_ids + stjulien_ids
    if all_covered_ids:
        placeholders = ','.join('?' * len(all_covered_ids))
        c.execute(f"DELETE FROM unites_fonctionnelles WHERE hospital_id IN ({placeholders})",
                  all_covered_ids)

    created = 0
    already = set()  # Éviter doublons (code_uf, hospital_id)

    for uf in uf_data:
        code = uf['code_uf']
        libelle = uf['libelle']
        pole = uf['pole']
        site_tag = uf['site_tag']

        if site_tag == 'ANNECY':
            target_ids = annecy_ids
        elif site_tag == 'ST JULIEN':
            target_ids = stjulien_ids
        else:
            continue

        for h_id in target_ids:
            key = (code, h_id)
            if key in already:
                continue
            already.add(key)
            c.execute("INSERT INTO unites_fonctionnelles (hospital_id, code_uf, libelle, pole) VALUES (?,?,?,?)",
                      (h_id, code, libelle, pole))
            created += 1

    conn.commit()
    total = c.execute("SELECT COUNT(*) FROM unites_fonctionnelles").fetchone()[0]
    by_site = c.execute("""SELECT h.nom, COUNT(u.id) FROM hospitals h
        LEFT JOIN unites_fonctionnelles u ON h.id=u.hospital_id
        GROUP BY h.id ORDER BY h.id""").fetchall()
    conn.close()

    print(f"  {label}: {created} UF injectées (total {total})")
    for nom, nb in by_site:
        status = "✓" if nb > 0 else "—"
        print(f"    {status} {nom[:45]}: {nb} UF")


def seed_demo_ufs_from_chag(db_path: str, label: str):
    """GHTs démo: pôles CHV avec jusqu'à 5 UF représentatives par pôle."""
    if not Path(db_path).exists():
        print(f"  {label}: DB absente — skip"); return
    if not JSON_PATH.exists():
        print(f"  {label}: JSON absent — skip"); return

    with open(JSON_PATH, encoding='utf-8') as f:
        uf_data = json.load(f)

    # Extraire les pôles et 5 UF ANNECY max par pôle
    poles: dict = {}
    for uf in uf_data:
        if uf['site_tag'] != 'ANNECY':
            continue
        p = uf['pole']
        if p not in poles:
            poles[p] = []
        if len(poles[p]) < 5:
            poles[p].append({'code_uf': uf['code_uf'], 'libelle': uf['libelle']})

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS unites_fonctionnelles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_id INTEGER NOT NULL,
        code_uf TEXT, libelle TEXT NOT NULL, pole TEXT
    )""")

    sites = c.execute("SELECT id, nom FROM hospitals ORDER BY id").fetchall()
    if not sites:
        conn.close(); return

    c.execute("DELETE FROM unites_fonctionnelles")
    created = 0
    for idx, (h_id, h_nom) in enumerate(sites):
        selected = list(poles.items()) if idx == 0 else [
            (p, ufs) for p, ufs in poles.items()
            if p in ('URGENCES', 'MEDECINE', 'CHIRURGIE ANESTHESIE', 'SUPPORT', 'SOINS CRITIQUES')
        ]
        for pole, ufs in selected:
            limit = ufs if idx == 0 else ufs[:3]
            for uf in limit:
                c.execute("INSERT INTO unites_fonctionnelles (hospital_id, code_uf, libelle, pole) VALUES (?,?,?,?)",
                          (h_id, uf['code_uf'], uf['libelle'], pole))
                created += 1

    conn.commit()
    total = c.execute("SELECT COUNT(*) FROM unites_fonctionnelles").fetchone()[0]
    conn.close()
    print(f"  {label}: {created} UF injectées (pôles CHV, total {total})")


if __name__ == '__main__':
    db_arg = sys.argv[1] if len(sys.argv) > 1 else None

    if db_arg:
        label = Path(db_arg).stem.upper()
        if 'chag' in db_arg.lower():
            seed_chag_ufs(db_arg, label)
        else:
            seed_demo_ufs_from_chag(db_arg, label)
    else:
        print("Seed UF — référentiel CHV 2026")
        print("=" * 50)
        instances = [
            (str(BASE / "scribe_chag.db"),  "CHV",    "chag"),
            (str(BASE / "scribe_ght2.db"),  "GHT1",  "demo"),
            (str(BASE / "scribe_ght3.db"),  "GHT2",  "demo"),
            (str(BASE / "scribe_ght4.db"),  "GHT3", "demo"),
        ]
        for db_path, label, mode in instances:
            try:
                if mode == "chag":
                    seed_chag_ufs(db_path, label)
                else:
                    seed_demo_ufs_from_chag(db_path, label)
            except Exception as e:
                print(f"  {label}: ERREUR {e}")
        print("=" * 50)
