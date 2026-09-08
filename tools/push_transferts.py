#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/push_transferts.py — Pousse les transferts des instances vers le
collecteur de supervision.

Pourquoi ce script existe
-------------------------
Les transferts inter-etablissements ne remontent pas par le push periodique de
federation. Ils sont envoyes un par un, au moment ou l utilisateur cree le
transfert ou change son statut, par la fonction trPushCollecteur() de
scribe.js. C est un choix assume : le collecteur recoit l information
immediatement, sans attendre le cycle de 30 secondes.

Consequence : des transferts ecrits directement en base — par le jeu de
donnees de demonstration, par un import, par une restauration — existent dans
l instance mais restent invisibles en supervision. Aucune interface ne les a
jamais pousses.

Deux vues, deux stockages
-------------------------
La supervision affiche les transferts a deux endroits, alimentes differemment :

  CARTOGRAPHIE  ambulances sur la carte, lit la liste transferts_inter.
                Alimentee par POST /api/push-transfert, avec le jeton de
                federation de l instance emettrice.

  TRANSFERTS    kanban a cinq colonnes, lit une base SQLite dediee.
                Alimentee par POST /api/admin/transferts-supervision, avec le
                jeton admin du collecteur.

Le script remplit les deux. Le mode kanban est le plus complet : a la creation,
le collecteur reinjecte lui-meme l entree dans transferts_inter, donc la carte
se remplit aussi.

Aucune donnee patient n est transmise. Le kanban accepte des champs nominatifs
— la supervision peut saisir un transfert elle-meme — mais ce script ne les
renseigne jamais : seuls le flux, l age estime et le motif circulent.

Aucune donnee patient n est transmise. La charge utile ne contient que le flux
— unites, etablissements, statut, heure d arrivee estimee — conformement a ce
que fait deja l interface. Les noms, prenoms et identifiants patients ne
quittent jamais l instance.

Usage :
    python3 tools/push_transferts.py --dry-run    # montrer sans envoyer
    python3 tools/push_transferts.py              # pousser
    python3 tools/push_transferts.py --ports 8000 8001
"""

import argparse
import json
import os
import pathlib
import sqlite3
import sys
import urllib.error
import urllib.request

RACINE = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = pathlib.Path(os.environ.get("SCRIBE_DATA_DIR") or (RACINE / "data" / "instances"))
STATE_FILE = pathlib.Path(os.environ.get("SCRIBE_STATE_FILE") or (RACINE / "master" / "master_instances.json"))
PORTS_DEFAUT = list(range(8000, 8008))

# Statuts qui ont un sens en supervision. Un transfert annule n a jamais ete
# pousse par l interface non plus : on ne le rejoue pas.
STATUTS_POUSSES = {"EN_PREPARATION", "EN_COURS", "ARRIVE"}


# ── Decouverte des instances (meme logique que tools/demo_data.py) ───────────

def _collecter(obj, sortie):
    if isinstance(obj, dict):
        if "port" in obj:
            sortie.append(obj)
        cfg = obj.get("config")
        if isinstance(cfg, dict) and "port" in cfg:
            sortie.append(cfg)
        for v in obj.values():
            _collecter(v, sortie)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collecter(v, sortie)


def instances(ports):
    par_port = {}
    if STATE_FILE.exists():
        try:
            trouves = []
            _collecter(json.loads(STATE_FILE.read_text(encoding="utf-8")), trouves)
            for e in trouves:
                try:
                    port = int(e.get("port"))
                except (TypeError, ValueError):
                    continue
                sigle = str(e.get("sigle") or "").strip()
                if port in ports and sigle and port not in par_port:
                    par_port[port] = sigle
        except Exception as exc:
            print("  Lecture de %s impossible (%s), balayage du disque."
                  % (STATE_FILE.name, exc))

    dossiers = []
    if DATA_DIR.exists():
        for d in sorted(DATA_DIR.iterdir()):
            if (d / "scribe.db").exists():
                dossiers.append(d)

    resultat, utilises = [], set()
    for port in ports:
        sigle = par_port.get(port)
        if not sigle:
            continue
        db = DATA_DIR / sigle / "scribe.db"
        if db.exists():
            resultat.append((port, sigle, db))
            utilises.add(db.parent)

    libres = [p for p in ports if p not in {r[0] for r in resultat}]
    for port, d in zip(libres, [x for x in dossiers if x not in utilises]):
        resultat.append((port, d.name, d / "scribe.db"))

    resultat.sort(key=lambda r: r[0])
    return resultat


def lire_config_js(db):
    """Sigle, nom, URL du collecteur et jeton, lus dans le config.js voisin de
    la base. C est le fichier que federation.py consulte lui-meme."""
    chemin = pathlib.Path(db).parent / "config.js"
    if not chemin.is_file():
        return {}
    try:
        brut = chemin.read_text(encoding="utf-8")
        i = brut.index("const SCRIBE_CONFIG = ") + len("const SCRIBE_CONFIG = ")
        cfg = json.loads(brut[i:brut.rindex(";")])
    except Exception:
        return {}
    etb = cfg.get("etablissement", {}) or {}
    fed = cfg.get("federation", {}) or {}
    return {
        "sigle": (etb.get("sigle") or "").strip(),
        "nom": (etb.get("nom") or "").strip(),
        "collecteur_url": (fed.get("collecteur_url") or "").strip(),
        "token": (fed.get("token") or "").strip(),
        "enabled": str(fed.get("enabled", "false")).lower() == "true",
    }


# ── Push ─────────────────────────────────────────────────────────────────────

def transferts(db):
    cx = sqlite3.connect(str(db), timeout=10)
    cx.row_factory = sqlite3.Row
    try:
        cur = cx.execute(
            "SELECT id, unite_origine, etablissement_origine, unite_destination, "
            "       etablissement_destination, site_destination, statut, eta, "
            "       horodatage_depart, commentaire "
            "FROM transferts_patients ORDER BY id"
        )
        return [dict(r) for r in cur]
    except sqlite3.Error:
        return []
    finally:
        cx.close()


def pousser(base_collecteur, jeton, charge, timeout=10):
    url = base_collecteur.rstrip("/") + "/api/push-transfert"
    data = json.dumps(charge, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": "Bearer " + jeton,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            return rep.status, rep.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def jeton_admin(explicite=None):
    """Jeton admin du collecteur : argument, variable d environnement, puis
    fichier de persistance — dans le meme ordre que le collecteur lui-meme."""
    if explicite:
        return explicite.strip()
    if os.environ.get("ADMIN_TOKEN"):
        return os.environ["ADMIN_TOKEN"].strip()
    for chemin in (RACINE / "collecteur" / "collecteur_admin.json",
                   pathlib.Path(os.environ.get("COLLECTEUR_ADMIN", ""))):
        try:
            if chemin and chemin.is_file():
                return (json.loads(chemin.read_text(encoding="utf-8"))
                        .get("admin_token", "") or "").strip()
        except Exception:
            continue
    return ""


def appel_admin(base, jeton, chemin, charge=None, methode="GET", timeout=10):
    url = base.rstrip("/") + chemin
    data = json.dumps(charge, ensure_ascii=False).encode("utf-8") if charge is not None else None
    entetes = {"Authorization": "Bearer " + jeton}
    if data is not None:
        entetes["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=methode, headers=entetes)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            corps = rep.read().decode("utf-8", "replace")
            return rep.status, (json.loads(corps) if corps.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def pousser_kanban(a, cibles):
    """Cree les transferts dans le kanban de supervision.

    A la creation, le collecteur reinjecte lui-meme l entree dans
    transferts_inter : la carte se remplit donc en meme temps.
    """
    jeton = jeton_admin(a.admin_token)
    if not jeton:
        print("  Jeton admin introuvable. Le preciser avec --admin-token,")
        print("  ou verifier collecteur/collecteur_admin.json.")
        return 0, 0

    code, existants = appel_admin(a.collecteur, jeton, "/api/admin/transferts-supervision")
    if code != 200:
        print("  Lecture du kanban impossible (HTTP %s) : %s" % (code, str(existants)[:120]))
        return 0, 0

    # Empreinte des transferts deja presents, pour ne pas dupliquer a chaque
    # execution du script.
    deja = {(str(t.get("etablissement_origine", "")).upper(),
             str(t.get("etablissement_destination", "")).upper(),
             str(t.get("unite_origine", "")).lower())
            for t in (existants or [])}

    crees = doublons = echecs = 0

    for port, sigle, db in cibles:
        cfg = lire_config_js(db)
        mon_sigle = (cfg.get("sigle") or sigle).upper()
        for t in transferts(db):
            statut = (t["statut"] or "").upper()
            if not a.tous_statuts and statut not in STATUTS_POUSSES:
                continue
            dest = (t["etablissement_destination"] or "").strip()
            if not dest or dest.upper() == mon_sigle:
                continue

            cle = (mon_sigle, dest.upper(), (t["unite_origine"] or "").lower())
            if cle in deja:
                doublons += 1
                continue

            charge = {
                "etablissement_origine": mon_sigle,
                "unite_origine": t["unite_origine"] or "",
                "etablissement_destination": dest,
                "unite_destination": t["unite_destination"] or "",
                # Rien de nominatif : le flux, pas le patient.
                "age_estime": ["42 ans", "67 ans", "78 ans", "35 ans", "59 ans"][t["id"] % 5],
                "sexe": ["H", "F"][t["id"] % 2],
                "motif": (t["commentaire"] or "Transfert inter-etablissements")[:120],
                "eta": t["eta"] or "",
                "commentaire": t["commentaire"] or "",
                "redacteur": "Supervision",
            }

            if a.dry_run:
                print("      %-8s -> %-8s %-14s %s"
                      % (mon_sigle, dest.upper(), statut, charge["motif"][:38]))
                crees += 1
                deja.add(cle)
                continue

            code, rep = appel_admin(a.collecteur, jeton,
                                    "/api/admin/transferts-supervision",
                                    charge, "POST")
            if code != 200 or not isinstance(rep, dict):
                echecs += 1
                if echecs == 1:
                    print("      echec creation HTTP %s : %s" % (code, str(rep)[:120]))
                continue

            # La creation force EN_PREPARATION : on repositionne le statut reel
            # pour que le kanban montre des colonnes contrastees.
            if statut and statut != "EN_PREPARATION" and rep.get("id"):
                appel_admin(a.collecteur, jeton,
                            "/api/admin/transferts-supervision/%s/statut" % rep["id"],
                            {"statut": statut}, "PATCH")
            crees += 1
            deja.add(cle)

    print("  kanban   %d cree(s), %d deja present(s), %d echec(s)"
          % (crees, doublons, echecs))
    return crees, echecs


def main():
    ap = argparse.ArgumentParser(
        description="Rejoue le push des transferts vers la supervision",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
A utiliser apres une ecriture directe en base (donnees de demonstration,
import, restauration). Les transferts crees normalement depuis l interface
sont deja pousses, les repousser est sans effet de bord : le collecteur
reconnait le couple (etablissement emetteur, identifiant local) et met a jour
au lieu de dupliquer.
""")
    ap.add_argument("--ports", nargs="+", type=int, default=PORTS_DEFAUT)
    ap.add_argument("--dry-run", action="store_true",
                    help="afficher ce qui serait envoye, sans rien envoyer")
    ap.add_argument("--tous-statuts", action="store_true",
                    help="pousser aussi les transferts annules")
    ap.add_argument("--vue", choices=("carte", "kanban", "les-deux"),
                    default="les-deux",
                    help="vue a alimenter (defaut : les deux)")
    ap.add_argument("--collecteur", default="http://127.0.0.1:9000",
                    help="URL du collecteur pour le mode kanban")
    ap.add_argument("--admin-token", default=None,
                    help="jeton admin du collecteur (sinon lu dans "
                         "collecteur/collecteur_admin.json ou ADMIN_TOKEN)")
    a = ap.parse_args()

    cibles = instances(a.ports)
    if not cibles:
        print("\n  Aucune instance trouvee dans %s\n" % DATA_DIR)
        return 1

    print("\n  Push des transferts vers la supervision%s"
          % ("  (simulation)" if a.dry_run else ""))
    print("  " + "-" * 68)

    total = envoyes = ignores = echecs = 0

    if a.vue in ("kanban", "les-deux"):
        print("  Vue TRANSFERTS (kanban) — via le jeton admin du collecteur")
        c, e = pousser_kanban(a, cibles)
        envoyes += c
        echecs += e
        print()

    if a.vue == "kanban":
        print("  " + "-" * 68)
        print("  Termine. Ouvrir la supervision, onglet TRANSFERTS.\n")
        return 0 if not echecs else 1

    print("  Vue CARTOGRAPHIE — via le jeton de federation de chaque instance")

    for port, sigle, db in cibles:
        cfg = lire_config_js(db)
        mon_sigle = (cfg.get("sigle") or sigle).upper()
        collecteur = cfg.get("collecteur_url", "").replace("/api/push", "")
        jeton = cfg.get("token", "")

        trs = transferts(db)
        total += len(trs)

        if not trs:
            print("  %-8s port %d  aucun transfert" % (sigle, port))
            continue
        if not collecteur or not jeton:
            print("  %-8s port %d  %d transfert(s) — config.js sans collecteur "
                  "ou sans jeton, ignore" % (sigle, port, len(trs)))
            ignores += len(trs)
            continue
        if not cfg.get("enabled"):
            print("  %-8s port %d  %d transfert(s) — federation desactivee, ignore"
                  % (sigle, port, len(trs)))
            ignores += len(trs)
            continue

        ok = ko = saute = 0
        for t in trs:
            statut = (t["statut"] or "").upper()
            if not a.tous_statuts and statut not in STATUTS_POUSSES:
                saute += 1
                continue

            dest = (t["etablissement_destination"] or "").strip()
            # Un transfert interne ne remonte pas : l interface applique la
            # meme regle (destSigle === monSigle -> return).
            if not dest or dest.upper() == mon_sigle:
                saute += 1
                continue

            charge = {
                "id_local": t["id"],
                "ght_emetteur_nom": cfg.get("nom") or mon_sigle,
                "ght_destinataire": dest.upper(),
                "unite_origine": t["unite_origine"] or "",
                "etablissement_origine": t["etablissement_origine"] or "",
                "unite_destination": t["unite_destination"] or "",
                "etablissement_destination": dest,
                "site_destination": t["site_destination"] or dest,
                "statut": statut or "EN_PREPARATION",
                "eta": t["eta"],
                "horodatage_depart": t["horodatage_depart"],
                "commentaire": t["commentaire"],
            }

            if a.dry_run:
                print("      %-14s -> %-10s %-14s eta=%s"
                      % (charge["unite_origine"][:14], charge["ght_destinataire"],
                         charge["statut"], charge["eta"] or "-"))
                ok += 1
                continue

            code, corps = pousser(collecteur, jeton, charge)
            if code == 200:
                ok += 1
            else:
                ko += 1
                if ko == 1:
                    print("      echec HTTP %s : %s" % (code, corps[:120]))

        envoyes += ok
        echecs += ko
        ignores += saute
        print("  %-8s port %d  %d envoye(s), %d ignore(s), %d echec(s)"
              % (sigle, port, ok, saute, ko))

    print("  " + "-" * 68)
    print("  %d transfert(s) en base, %d %s, %d ignore(s), %d echec(s)."
          % (total, envoyes, "a envoyer" if a.dry_run else "envoye(s)",
             ignores, echecs))

    if not a.dry_run and envoyes:
        print("\n  Ouvrir la supervision : onglet TRANSFERTS pour le kanban,")
        print("  onglet CARTOGRAPHIE pour les ambulances en mouvement.")
    if echecs:
        print("\n  Les echecs viennent le plus souvent d un collecteur arrete,")
        print("  d un jeton non enrole, ou d une instance non acceptee cote admin.")
    print()
    return 0 if not echecs else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n  Interrompu.\n")
        sys.exit(130)
