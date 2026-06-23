"""
import_uf2.py — Importateur des Unités Fonctionnelles pour SCRIBE.

Supporte deux formats :
  • Format FICOM (export GEF/CPAGE des établissements publics)  → skiprows=10
  • Format modèle générique (uf_modele.xlsx fourni avec SCRIBE) → skiprows=8

Le script détecte automatiquement le format selon la ligne d'en-tête.

Usage :
  python import_uf2.py                   → lit uf.xlsx ou uf_modele.xlsx
  python import_uf2.py mon_fichier.xlsx  → chemin explicite

Configuration du SITE_MAPPING :
  Modifiez SITE_MAPPING pour faire correspondre les valeurs de la colonne 'Site'
  de votre fichier Excel aux noms d'hôpitaux déclarés dans seed.py.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from app.database import SessionLocal, engine, Base
import app.models  # noqa
from app.models import Hospital, UniteFonctionnelle


# ── SITE_MAPPING ──────────────────────────────────────────────────────────────
# Clé   = valeur dans la colonne 'Site' du fichier Excel (insensible à la casse)
# Valeur = liste des noms d'hôpitaux en base (exactement comme dans seed.py)
#
# Exemples pour le modèle générique (uf_modele.xlsx) :
SITE_MAPPING = {
    # Mapping FICOM CHAG → noms EXACTS des sites tels que dans config.xml CHAG
    # Valeurs colonne 'Site' dans uf.xlsx CHAG : ANNECY, BI SITE, ST JULIEN
    # Les noms ici doivent correspondre aux <nom> dans config.xml <sites>
    "ANNECY":       ["Site hospitalier principal Annecy"],
    "BI SITE":      ["Site hospitalier principal Annecy", "Hopital Saint-Julien"],
    "ST JULIEN":    ["Hopital Saint-Julien"],
    # Variantes avec accent (selon la version du config.xml)
    "SAINT-JULIEN": ["Hopital Saint-Julien", "Hôpital Saint-Julien"],
    "ST-JULIEN":    ["Hopital Saint-Julien", "Hôpital Saint-Julien"],
    # Compatibilité démo générique (config_demo1.xml)
    "SITE PRINCIPAL":  ["Site Principal — Valmont", "Site hospitalier principal Annecy"],
    "SITE SECONDAIRE": ["Site Secondaire — Crestval", "Hopital Saint-Julien"],
}
# Exemple pour un export FICOM d'un établissement bi-sites (Site A / Site B) :
# SITE_MAPPING = {
#     "ANNECY":    ["Site Principal A", "Site Annexe A"],
#     "ST JULIEN": ["Site Principal B"],
#     "BI SITE":   ["Site Principal A", "Site Principal B"],
# }
# ─────────────────────────────────────────────────────────────────────────────


def detect_skiprows(file_path: str) -> int:
    """Détecte automatiquement la ligne d'en-tête (contient 'N°UF' et 'Site')."""
    df_raw = pd.read_excel(file_path, header=None, nrows=20)
    for i, row in df_raw.iterrows():
        vals = [str(v) for v in row]
        if any("N°UF" in v or "NUF" in v.upper() for v in vals) and \
           any("Site" in v or "SITE" in v for v in vals):
            return i
    # Fallback : format FICOM standard
    return 10


def import_uf(file_path: str):
    if not os.path.exists(file_path):
        print(f"[!] Fichier introuvable : {file_path}")
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Détection automatique du format
        skiprows = detect_skiprows(file_path)
        print(f"[-] Format détecté : en-têtes à la ligne {skiprows + 1} (skiprows={skiprows})")

        # Suppression des UF existantes
        deleted = db.query(UniteFonctionnelle).delete()
        db.commit()
        if deleted:
            print(f"[~] {deleted} UF existantes supprimées.")

        df = pd.read_excel(file_path, skiprows=skiprows)
        print(f"[-] {len(df)} lignes lues dans {file_path}")

        # Vérification des colonnes obligatoires
        required = {"N°UF", "libellé UF", "Site"}
        missing  = required - set(df.columns)
        if missing:
            print(f"[!] Colonnes manquantes : {missing}")
            print(f"    Colonnes disponibles : {list(df.columns)}")
            return

        # Pré-charger les hôpitaux
        hospitals_cache = {h.nom: h for h in db.query(Hospital).all()}
        if not hospitals_cache:
            print("[!] Aucun hôpital en base — lancez d'abord : python seed.py")
            return

        # Normaliser le SITE_MAPPING (insensible à la casse)
        site_map_upper = {k.upper(): v for k, v in SITE_MAPPING.items()}

        count = skipped = 0
        pole_courant = ""

        for _, row in df.iterrows():
            if pd.isna(row.get("N°UF")) or pd.isna(row.get("Site")):
                # Récupérer le pôle des lignes séparatrices
                if pd.notna(row.get("libellé pôle")):
                    pole_courant = str(row["libellé pôle"]).strip()
                continue

            site_excel = str(row["Site"]).strip().upper()
            if site_excel not in site_map_upper:
                skipped += 1
                continue

            code_uf = str(row["N°UF"]).strip().replace(".0", "")
            libelle = str(row.get("libellé UF", "")).strip() or f"UF {code_uf}"

            # Pôle : depuis la ligne ou depuis la ligne séparatrice précédente
            pole = str(row.get("libellé pôle", "")).strip()
            if not pole or pole.lower() in ("nan", "none"):
                pole = pole_courant

            for nom_hosp in site_map_upper[site_excel]:
                # Recherche exacte d'abord, puis insensible à la casse/accents
                hospital = hospitals_cache.get(nom_hosp)
                if not hospital:
                    # Fallback 1 : insensible à la casse
                    nom_hosp_lower = nom_hosp.lower()
                    for nom_db, h in hospitals_cache.items():
                        if nom_db.lower() == nom_hosp_lower:
                            hospital = h
                            break
                if not hospital:
                    # Fallback 2 : mot-clé géographique dans le nom du site
                    # ex: "Annecy" matche "Site hospitalier principal Annecy"
                    # et aussi "Site Principal — Valmont" si config CHAG le nomme ainsi
                    mots_cles = [m for m in nom_hosp.lower().split() if len(m) > 3]
                    for nom_db, h in hospitals_cache.items():
                        nom_db_lower = nom_db.lower()
                        if all(m in nom_db_lower for m in mots_cles):
                            hospital = h
                            break
                if not hospital:
                    # Fallback 3 : chercher par ordre (ANNECY → premier site, ST JULIEN → second)
                    sites_list = list(hospitals_cache.values())
                    idx_map = {"ANNECY": 0, "BI SITE": 0, "ST JULIEN": 1, "SAINT-JULIEN": 1}
                    site_excel_key = site_excel.upper()
                    if site_excel_key in idx_map and idx_map[site_excel_key] < len(sites_list):
                        hospital = sites_list[idx_map[site_excel_key]]
                        # Silencieux — pas d'avertissement pour ce fallback
                    else:
                        print(f"  [?] Hopital '{nom_hosp}' absent de la base "
                              f"(sites disponibles: {list(hospitals_cache.keys())})")
                        continue
                db.add(UniteFonctionnelle(
                    code_uf=code_uf,
                    libelle=libelle,
                    pole=pole,
                    hospital_id=hospital.id,
                ))
                count += 1

            if count % 500 == 0 and count > 0:
                db.commit()
                print(f"  ... {count} UF insérées")

        db.commit()
        print(f"\n[✓] Import terminé : {count} UF insérées | {skipped} lignes ignorées.")
        if skipped > 0:
            print(f"    Conseil : vérifiez que les valeurs 'Site' de votre fichier")
            print(f"    correspondent aux clés de SITE_MAPPING dans ce script.")

    except Exception as e:
        db.rollback()
        print(f"[!] Erreur : {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # Chercher le fichier à importer
    if len(sys.argv) > 1:
        path = sys.argv[1]
    elif os.path.exists("uf_modele.xlsx"):
        path = "uf_modele.xlsx"
    elif os.path.exists("uf.xlsx"):
        path = "uf.xlsx"
    else:
        print("[!] Aucun fichier trouvé. Usage : python import_uf2.py mon_fichier.xlsx")
        sys.exit(1)

    import_uf(path)
