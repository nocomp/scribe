"""
SCRIBE — moteur de sauvegarde/restauration plug-and-play.
Capture l'intégralité d'une base SQLite (schéma + données) + des fichiers de
config, le tout dans une archive ZIP chiffrée en AES.

Conçu pour être appelé par l'app (endpoint export/restore) ET testable seul.
"""
import json, sqlite3, io, time, os, base64
import pyzipper

SCHEMA_VERSION = "4.0.0"


def _enc_val(v):
    if isinstance(v, (bytes, bytearray)):
        return {"__b64__": base64.b64encode(bytes(v)).decode("ascii")}
    return v


def _dec_val(v):
    if isinstance(v, dict) and "__b64__" in v:
        return base64.b64decode(v["__b64__"])
    return v

# Tables internes SQLite à ne jamais sauvegarder/restaurer
_SKIP_TABLES = {"sqlite_sequence", "sqlite_stat1", "sqlite_stat4"}


def dump_database(db_path):
    """Lit TOUT le contenu d'une base SQLite -> dict JSON-able.
    {schema:{table:create_sql}, data:{table:[ {col:val}, ... ]}, order:[tables]}"""
    con = sqlite3.connect(db_path)
    # Rapatrier un eventuel WAL non checkpointe (instance arretee brutalement) :
    # sinon les dernieres ecritures (ex: 2e utilisateur cree juste avant l'arret)
    # restent dans scribe.db-wal et echappent au dump.
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [(r["name"], r["sql"]) for r in cur.fetchall() if r["name"] not in _SKIP_TABLES]
    schema, data, order = {}, {}, []
    for name, sql in tables:
        schema[name] = sql
        rows = con.execute(f'SELECT * FROM "{name}"').fetchall()
        data[name] = [{k: _enc_val(v) for k, v in dict(r).items()} for r in rows]
        order.append(name)
    con.close()
    return {"schema": schema, "data": data, "order": order}


def collect(db_paths, config_files=None):
    """Assemble la charge complète : une ou plusieurs bases + fichiers de config.
    db_paths : { logical_name: filesystem_path }
    config_files : { stored_name: text_content }"""
    payload = {
        "manifest": {
            "scribe_version": SCHEMA_VERSION,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "databases": list(db_paths.keys()),
        },
        "databases": {name: dump_database(path) for name, path in db_paths.items()},
        "config_files": config_files or {},
    }
    return payload


def make_encrypted_zip(payload, password):
    """payload(dict) -> bytes d'un ZIP AES protégé par mot de passe."""
    buf = io.BytesIO()
    with pyzipper.AESZipFile(buf, "w", compression=pyzipper.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.writestr("manifest.json", json.dumps(payload["manifest"], ensure_ascii=False, indent=2))
        zf.writestr("backup.json", json.dumps(payload, ensure_ascii=False))
    return buf.getvalue()


def read_encrypted_zip(zip_bytes, password):
    """bytes ZIP AES + mot de passe -> payload(dict). Lève une erreur si mdp faux."""
    buf = io.BytesIO(zip_bytes)
    with pyzipper.AESZipFile(buf, "r") as zf:
        zf.setpassword(password.encode("utf-8"))
        raw = zf.read("backup.json")   # lève RuntimeError si mauvais mot de passe
    return json.loads(raw.decode("utf-8"))


def restore_database(dest_db_path, db_payload):
    """Recrée tables + données d'une base à partir du dump. Remplacement complet."""
    con = sqlite3.connect(dest_db_path)
    con.execute("PRAGMA foreign_keys=OFF")
    cur = con.cursor()
    for name in db_payload["order"]:
        cur.execute(f'DROP TABLE IF EXISTS "{name}"')
        cur.execute(db_payload["schema"][name])
        rows = db_payload["data"][name]
        if rows:
            cols = list(rows[0].keys())
            ph = ",".join("?" * len(cols))
            collist = ",".join(f'"{c}"' for c in cols)
            cur.executemany(
                f'INSERT INTO "{name}" ({collist}) VALUES ({ph})',
                [[_dec_val(r[c]) for c in cols] for r in rows],
            )
    con.commit()
    con.execute("PRAGMA foreign_keys=ON")
    con.close()


def restore(payload, db_paths, config_dir=None):
    """Applique une sauvegarde : restaure chaque base, réécrit les configs."""
    for name, db in payload["databases"].items():
        if name in db_paths:
            restore_database(db_paths[name], db)
    if config_dir:
        for fname, content in payload.get("config_files", {}).items():
            with open(os.path.join(config_dir, fname), "w", encoding="utf-8") as f:
                f.write(content)
