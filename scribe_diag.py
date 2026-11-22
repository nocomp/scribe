#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCRIBE — Diagnostic complet sauvegarde / données.

À placer à la RACINE du dossier SCRIBE (à côté de master/, collecteur/, data/)
puis lancer :   python3 scribe_diag.py

Produit un fichier  scribe_diag_<horodatage>.log  + affichage console.
Aucune donnée sensible (hash, secret) n'est révélée : tout est masqué.
"""
import os, sys, json, glob, sqlite3, datetime, traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = os.path.join(ROOT, f"scribe_diag_{TS}.log")
_lines = []


def log(msg=""):
    print(msg)
    _lines.append(str(msg))


def section(title):
    log("")
    log("=" * 78)
    log(title)
    log("=" * 78)


def mask(v):
    if not v:
        return "(vide)"
    s = str(v)
    return s[:4] + "…" + s[-2:] if len(s) > 8 else "***"


def resolve_paths():
    data_dir = os.environ.get("SCRIBE_DATA_DIR") or os.path.join(ROOT, "data", "instances")
    state_file = os.environ.get("SCRIBE_STATE_FILE") or os.path.join(ROOT, "master", "master_instances.json")
    coll = os.path.join(ROOT, "collecteur")
    return data_dir, state_file, coll


def dump_db_summary(db_path):
    """Renvoie (tables_non_vides:dict, users:list) ou (None, erreur)."""
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        tabs = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
        counts = {}
        for t in tabs:
            try:
                n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                if n:
                    counts[t] = n
            except Exception:
                counts[t] = "?"
        users = []
        if "users" in tabs:
            cols = [r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()]
            want = [c for c in ("id", "username", "role", "active", "email", "telephone",
                                "must_change_password", "created_at") if c in cols]
            for r in con.execute(f'SELECT {",".join(want)} FROM users').fetchall():
                users.append({k: r[k] for k in want})
        con.close()
        return counts, users
    except Exception as e:
        return None, f"ERREUR sqlite: {e}"


def main():
    data_dir, state_file, coll = resolve_paths()

    section("CONTEXTE")
    log(f"Racine projet      : {ROOT}")
    log(f"SCRIBE_DATA_DIR    : {os.environ.get('SCRIBE_DATA_DIR') or '(non défini)'}")
    log(f"SCRIBE_STATE_FILE  : {os.environ.get('SCRIBE_STATE_FILE') or '(non défini)'}")
    log(f"Dossier données    : {data_dir}  (existe={os.path.isdir(data_dir)})")
    log(f"Fichier état master: {state_file}  (existe={os.path.isfile(state_file)})")
    log(f"Dossier collecteur : {coll}  (existe={os.path.isdir(coll)})")
    log(f"Horodatage         : {datetime.datetime.now().isoformat()}")

    # ----------------------------------------------------------------
    section("1. TOUTES LES BASES SQLite TROUVÉES (où qu'elles soient)")
    seen = set()
    search_roots = [data_dir, os.path.join(ROOT, "data"), ROOT]
    found = []
    for sr in search_roots:
        for db in glob.glob(os.path.join(sr, "**", "scribe.db"), recursive=True):
            rp = os.path.realpath(db)
            if rp not in seen:
                seen.add(rp)
                found.append(db)
    if not found:
        log("  Aucune base scribe.db trouvée.")
    for db in sorted(found):
        log("")
        log(f">> {db}")
        counts, users = dump_db_summary(db)
        if counts is None:
            log(f"   {users}")
            continue
        log(f"   tables non vides : {counts}")
        if users:
            log(f"   USERS ({len(users)}) :")
            for u in users:
                log(f"      - {u}")
        else:
            log("   USERS : aucun (table users vide ou absente)")

    # ----------------------------------------------------------------
    section("2. ÉTAT DU MASTER (master_instances.json)")
    try:
        d = json.load(open(state_file, encoding="utf-8"))
        items = d if isinstance(d, list) else list(d.values()) if isinstance(d, dict) else []
        log(f"  {len(items)} instance(s) enregistrée(s) :")
        for x in items:
            c = (x.get("config") or {}) if isinstance(x, dict) else {}
            dbp = x.get("db_path") if isinstance(x, dict) else None
            exists = os.path.isfile(dbp) if dbp else False
            nuser = "?"
            if exists:
                _, us = dump_db_summary(dbp)
                nuser = len(us) if isinstance(us, list) else us
            log(f"   - port={c.get('port')} sigle={c.get('sigle')!r} statut={x.get('statut')}")
            log(f"       admin_login={c.get('admin_login')} db_path={dbp}")
            log(f"       db_path existe={exists}  users_dans_cette_base={nuser}")
    except Exception as e:
        log(f"  ERREUR lecture {state_file} : {e}")

    # ----------------------------------------------------------------
    section("3. COMPTES SUPERVISION (collecteur_ui_auth.json)")
    uiauth = os.path.join(coll, "collecteur_ui_auth.json")
    if os.path.isfile(uiauth):
        try:
            a = json.load(open(uiauth, encoding="utf-8"))
            log(f"  Structure : type={type(a).__name__}")
            # peut être {login, password_hash} OU {users:[...]} OU {login:{...}}
            def show(obj, indent="   "):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if "hash" in k.lower() or "pass" in k.lower() or "token" in k.lower():
                            log(f"{indent}{k}: {mask(v)}")
                        elif isinstance(v, (dict, list)):
                            log(f"{indent}{k}:")
                            show(v, indent + "  ")
                        else:
                            log(f"{indent}{k}: {v}")
                elif isinstance(obj, list):
                    for i, it in enumerate(obj):
                        log(f"{indent}[{i}]")
                        show(it, indent + "  ")
            show(a)
        except Exception as e:
            log(f"  ERREUR lecture : {e}")
    else:
        log("  (fichier absent)")

    # ----------------------------------------------------------------
    section("4. CONFIG NOTIF SERVEUR (collecteur_central_config.json)")
    cc = os.path.join(coll, "collecteur_central_config.json")
    if os.path.isfile(cc):
        try:
            raw = json.load(open(cc, encoding="utf-8"))
            log("  Fichier présent. Champs par canal (secrets masqués) :")
            for domain, fields in raw.items():
                if isinstance(fields, dict):
                    summary = {}
                    for k, v in fields.items():
                        if any(s in k.lower() for s in ("pass", "secret", "key", "token")):
                            summary[k] = mask(v) if v else "(vide)"
                        else:
                            summary[k] = v
                    log(f"   [{domain}] {summary}")
                else:
                    log(f"   {domain}: {fields}")
        except Exception as e:
            log(f"  ERREUR lecture : {e}")
        # tentative de déchiffrement via le store officiel
        try:
            sys.path.insert(0, coll)
            import central_config_store as ccs
            clear = ccs.load_clear()
            log("")
            log("  Déchiffré (load_clear) — un host/provider non vide = canal configuré :")
            for domain, fields in (clear or {}).items():
                if isinstance(fields, dict):
                    key = fields.get("smtp_host") or fields.get("provider") or fields.get("host") or ""
                    log(f"   [{domain}] configuré={'OUI' if key else 'non'}  (repère='{key}')")
        except Exception as e:
            log(f"  (déchiffrement indisponible : {e})")
    else:
        log("  (ABSENT — aucune notif enregistrée côté serveur, ou jamais 'Enregistré')")

    # ----------------------------------------------------------------
    section("5. SIMULATION DU BACKUP — ce que l'archive contiendrait MAINTENANT")
    try:
        sys.path.insert(0, ROOT)
        from app import backup as _bk
        engine_ok = True
    except Exception as e:
        engine_ok = False
        log(f"  Moteur app.backup non importable : {e}")
    try:
        if not os.path.isfile(state_file):
            raise FileNotFoundError(f"{state_file} absent — aucune instance enregistrée côté master")
        d = json.load(open(state_file, encoding="utf-8"))
        items = d if isinstance(d, list) else list(d.values()) if isinstance(d, dict) else []
        total_capt = 0
        for x in items:
            c = (x.get("config") or {})
            sigle = c.get("sigle")
            dbp = x.get("db_path")
            if not dbp or not os.path.isfile(dbp):
                # fallback comme l'endpoint
                if sigle:
                    cand = os.path.join(data_dir, sigle, "scribe.db")
                    if os.path.isfile(cand):
                        dbp = cand
            if dbp and os.path.isfile(dbp):
                counts, users = dump_db_summary(dbp)
                rows = sum(v for v in counts.values() if isinstance(v, int)) if isinstance(counts, dict) else 0
                unames = [u.get("username") for u in users] if isinstance(users, list) else users
                total_capt += rows
                log(f"  CAPTURÉ -> {sigle} | {dbp}")
                log(f"            users={unames} | total_lignes={rows}")
            else:
                log(f"  IGNORÉ  -> {sigle} (pas de base sur disque)")
        # config serveur
        sc_present = os.path.isfile(cc)
        log("")
        log(f"  + config notif serveur incluse (h129+) : {'OUI' if sc_present else 'NON (fichier absent)'}")
        log(f"  + comptes supervision (collecteur_ui_auth.json) : "
            f"{'présents sur disque mais PAS encore inclus dans le backup' if os.path.isfile(uiauth) else 'absents'}")
        log(f"  TOTAL lignes instances qui partiraient dans l'archive : {total_capt}")
    except Exception as e:
        log(f"  Simulation impossible : {e}")

    # ----------------------------------------------------------------
    section("CONCLUSION RAPIDE (à me coller)")
    log("  Cherche dans le bloc 1 / 2 où apparaît 'rssi' :")
    log("   - dans un scribe.db  -> user d'INSTANCE (le backup doit le prendre)")
    log("   - dans collecteur_ui_auth.json -> compte SUPERVISION (hors backup actuel)")
    log("   - nulle part -> la création n'a pas persisté")
    log("  Bloc 4 : notif présente côté serveur ? (sinon 'Enregistrer' n'a rien fait)")

    open(LOG_PATH, "w", encoding="utf-8").write("\n".join(_lines))
    print("")
    print(f"==> Log complet écrit dans : {LOG_PATH}")
    print("    Colle-moi son contenu (ou envoie le fichier).")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
