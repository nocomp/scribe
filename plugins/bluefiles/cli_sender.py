"""
plugins/bluefiles/cli_sender.py — SCRIBE
=========================================
Intégration RÉELLE de l'utilitaire d'envoi BlueFiles (binaire CLI fourni par
Forecomm — doc « Utilitaire d'envoi BlueFiles v1.11 »).

Contrairement à client.py (ébauche basée sur une API REST hypothétique), ce
module pilote le binaire ``tools/BlueFilesTransfer`` via un fichier de
configuration JSON, qui décrit l'envoi en une seule passe :

    ./tools/BlueFilesTransfer -json <config.json>     (code retour 0 = succès)

Workflow SCRIBE :
    fichier déposé sur la zone  ──►  stocké dans plugins/bluefiles/data/
                                ──►  cli_sender.send_files_cli(...)
                                ──►  un appel binaire  ──►  envoyé / erreur

Sécurité (non négociable) :
    - Les identifiants sont lus UNIQUEMENT depuis l'environnement, jamais en
      dur dans le code, jamais committés, jamais stockés en DB.
        SCRIBE_BLUEFILES_LOGIN     (compte API)
        SCRIBE_BLUEFILES_PASSWORD  (mot de passe API)
        SCRIBE_BLUEFILES_SERVER    (domaine du serveur BlueFiles)
        SCRIBE_BLUEFILES_IMPERSONATE (facultatif)
    - Le fichier de config JSON contient le mot de passe API EN CLAIR : il est
      écrit dans un fichier temporaire en 0600 puis SUPPRIMÉ immédiatement
      après l'appel (bloc finally), succès comme échec.
    - Dépendance serveur : libxerces-c3.2  (apt install -y libxerces-c3.2).
"""
import os
import re
import json
import stat
import pathlib
import logging
import tempfile
import subprocess

logger = logging.getLogger("scribe.plugins.bluefiles.cli")

PLUGIN_DIR = pathlib.Path(__file__).resolve().parent
TOOLS_DIR  = PLUGIN_DIR / "tools"
DATA_DIR   = PLUGIN_DIR / "data"
BINARY     = TOOLS_DIR / "BlueFilesTransfer"


def ensure_binary_exec() -> None:
    """Restaure le bit exécutable du binaire CLI s'il a été perdu (extraction de
    ZIP, copie sans préservation des droits…). Idempotent et silencieux."""
    try:
        if BINARY.exists() and not os.access(str(BINARY), os.X_OK):
            os.chmod(str(BINARY), 0o755)
    except Exception:
        pass


# Appliqué dès l'import du module : un binaire non exécutable était l'une des
# causes de bascule silencieuse en simulation.
ensure_binary_exec()


# ── Configuration (environnement uniquement) ─────────────────────────────────
def _env(*names: str, default: str = "") -> str:
    """Première variable d'environnement non vide parmi `names`."""
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return default


def get_cli_config() -> dict:
    """Config CLI effective. Priorité : DB (admin) > environnement > défaut.

    Lue depuis la table plugin_bluefiles_config (champs cli_*), éditable via
    l'admin → Plugins. Repli sur les variables d'environnement si la DB est
    vide/indisponible. Le serveur a une valeur par défaut (api.bluefiles.com).
    """
    cfg = {
        "login":       _env("SCRIBE_BLUEFILES_LOGIN", "BLUEFILES_LOGIN"),
        "password":    _env("SCRIBE_BLUEFILES_PASSWORD", "BLUEFILES_PASSWORD"),
        # Valeur fixe confirmée par Forecomm : le domaine du serveur BlueFiles
        # est « api.bluefiles.com ». Surchargeable par DB ou environnement.
        "server":      _env("SCRIBE_BLUEFILES_SERVER", "BLUEFILES_SERVER",
                            default="api.bluefiles.com"),
        "impersonate": _env("SCRIBE_BLUEFILES_IMPERSONATE", "BLUEFILES_IMPERSONATE"),
    }
    # Couche CENTRALE (supervision) — si le domaine bluefiles est diffusé (enabled).
    # Précédence finale : DB locale (ci-dessous) > centrale > env/défaut. Sans ce
    # palier, une config BlueFiles posée dans la supervision n'atteignait jamais
    # le CLI de l'instance (cause : config supervision non fonctionnelle).
    try:
        from app.central_config import get_domain as _cc_get
        cc = _cc_get("bluefiles")
        if cc and cc.get("enabled"):
            if (cc.get("login") or "").strip():
                cfg["login"] = cc["login"].strip()
            if (cc.get("password") or "").strip():
                cfg["password"] = cc["password"].strip()
            if (cc.get("server") or "").strip():
                cfg["server"] = cc["server"].strip()
    except Exception:
        pass
    # Surcharge DB (prioritaire) — ne jamais échouer si table/colonnes absentes
    try:
        from app.database import SessionLocal
        from plugins.bluefiles.models import BluefilesConfig
        db = SessionLocal()
        try:
            row = db.query(BluefilesConfig).filter_by(id=1).first()
            if row:
                if (getattr(row, "cli_login", "") or "").strip():
                    cfg["login"] = row.cli_login.strip()
                if (getattr(row, "cli_password", "") or "").strip():
                    from plugins.bluefiles import crypto as _bfcrypto
                    cfg["password"] = _bfcrypto.dec(row.cli_password.strip())
                if (getattr(row, "cli_server", "") or "").strip():
                    cfg["server"] = row.cli_server.strip()
                if (getattr(row, "cli_impersonate", "") or "").strip():
                    cfg["impersonate"] = row.cli_impersonate.strip()
        finally:
            db.close()
    except Exception:
        pass  # DB indisponible → on garde env + défaut
    return cfg


def cli_available() -> bool:
    """True si le binaire est présent + exécutable ET les identifiants présents."""
    ensure_binary_exec()
    c = get_cli_config()
    return (
        BINARY.exists()
        and os.access(str(BINARY), os.X_OK)
        and bool(c["login"] and c["password"] and c["server"])
    )


def cli_diagnostic() -> dict:
    """État détaillé pour l'admin/diagnostic, SANS exposer les secrets."""
    c = get_cli_config()
    return {
        "binary_present": BINARY.exists(),
        "binary_exec":    BINARY.exists() and os.access(str(BINARY), os.X_OK),
        "binary_path":    str(BINARY),
        "has_login":      bool(c["login"]),
        "has_password":   bool(c["password"]),
        "has_server":     bool(c["server"]),
        "impersonate":    bool(c["impersonate"]),
        "data_dir":       str(DATA_DIR),
        "password_unreadable": password_unreadable(),
        "ready":          cli_available(),
    }


def password_unreadable() -> bool:
    """True si un mot de passe CHIFFRÉ est stocké en DB mais ne se déchiffre pas.

    C'est le symptôme d'une clé de chiffrement instable (SCRIBE_SECRET / SECRET_KEY
    différente entre l'enregistrement et la lecture). Dans ce cas le plugin
    retombait silencieusement en simulation : on veut désormais le détecter et le
    signaler clairement à l'admin (ré-saisir le mot de passe)."""
    try:
        from app.database import SessionLocal
        from plugins.bluefiles.models import BluefilesConfig
        from plugins.bluefiles import crypto as _bfcrypto
        db = SessionLocal()
        try:
            row = db.query(BluefilesConfig).filter_by(id=1).first()
            if not row:
                return False
            raw = (getattr(row, "cli_password", "") or "")
            if not raw or not _bfcrypto.is_encrypted(raw):
                return False  # vide ou clair (legacy) → lisible
            return _bfcrypto.dec(raw) == ""  # chiffré mais déchiffrement vide = échec
        finally:
            db.close()
    except Exception:
        return False


def unavailable_reason() -> str:
    """Raison lisible (sans secret) expliquant pourquoi l'envoi CLI n'est pas prêt.
    Utilisée pour renvoyer une erreur explicite plutôt qu'une simulation muette."""
    diag = cli_diagnostic()
    if not diag["binary_present"]:
        return f"binaire d'envoi absent ({diag['binary_path']})"
    if not diag["binary_exec"]:
        return "binaire présent mais non exécutable (chmod +x requis sur le serveur)"
    if diag["password_unreadable"]:
        return ("mot de passe enregistré mais illisible : la clé de chiffrement "
                "(SCRIBE_SECRET) a changé depuis l'enregistrement. Ré-saisir le mot "
                "de passe BlueFiles dans l'administration.")
    c = get_cli_config()
    missing = [n for n, v in (("login", c["login"]),
                              ("mot de passe", c["password"]),
                              ("serveur", c["server"])) if not v]
    if missing:
        return "identifiants incomplets : " + ", ".join(missing) + " (à configurer dans l'admin)"
    return "configuration BlueFiles incomplète (voir le diagnostic dans l'administration)"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)


# ── Envoi via le binaire ─────────────────────────────────────────────────────
def send_files_cli(
    file_paths: list,
    recipients: list,
    *,
    object: str = "",
    message: str = "",
    note: str = "",
    transfer_password: str | None = None,
    bluepass_mandatory: bool = True,
    ar_default: bool = False,
    allow_reply: bool = True,
    verbose: bool = False,
    timeout: int = 1800,
) -> dict:
    """Réalise un envoi BlueFiles en pilotant le binaire CLI.

    file_paths : list[str|Path] — fichiers à envoyer (doivent exister sur disque,
                 typiquement dans plugins/bluefiles/data/).
    recipients : list[dict]     — [{"email": "x@y.fr", "acknowledge": bool?}, ...]

    Retour : {
        "ok": bool, "returncode": int, "raw": str,
        "uuid"?: str, "short_link"?: str, "error"?: str
    }
    """
    c = get_cli_config()
    if not (c["login"] and c["password"] and c["server"]):
        return {"ok": False, "returncode": -1, "raw": "",
                "error": "Identifiants BlueFiles absents "
                         "(SCRIBE_BLUEFILES_LOGIN / _PASSWORD / _SERVER)"}
    if not BINARY.exists():
        return {"ok": False, "returncode": -1, "raw": "",
                "error": f"Binaire absent : {BINARY}"}
    if not os.access(str(BINARY), os.X_OK):
        return {"ok": False, "returncode": -1, "raw": "",
                "error": f"Binaire non exécutable : {BINARY} (chmod +x requis)"}

    # Fichiers → format attendu {path, name}
    files = []
    for p in file_paths:
        pp = pathlib.Path(p)
        if not pp.exists():
            return {"ok": False, "returncode": -1, "raw": "",
                    "error": f"Fichier introuvable : {pp}"}
        files.append({"path": str(pp.resolve()), "name": pp.name})
    if not files:
        return {"ok": False, "returncode": -1, "raw": "",
                "error": "Aucun fichier à envoyer"}

    # Destinataires → format attendu {email, acknowledge}
    recs = []
    for r in recipients:
        email = (r.get("email") or "").strip()
        if not email:
            continue
        recs.append({"email": email, "acknowledge": bool(r.get("acknowledge", ar_default))})
    if not recs:
        return {"ok": False, "returncode": -1, "raw": "",
                "error": "Aucun destinataire valide"}

    cfg_path = None
    log_path = None
    try:
        # Log dédié à ce traitement (parsé puis supprimé)
        lf = tempfile.NamedTemporaryFile(prefix="bf_log_", suffix=".log", delete=False)
        log_path = lf.name
        lf.close()

        cfg = {
            "login":              c["login"],
            "password":           c["password"],
            "server":             c["server"],
            "object":             object or "Document sécurisé — SCRIBE",
            "message":            message or "",
            "note":               note or "",
            "files":              files,
            "recipients":         recs,
            "bluepass_mandatory": bool(bluepass_mandatory),
            "allow_reply":        bool(allow_reply),
            "verbose":            bool(verbose),
            "log_file":           log_path,
        }
        if c["impersonate"]:
            cfg["impersonate"] = c["impersonate"]
        if transfer_password:
            cfg["transfer_password"] = transfer_password

        # Config JSON éphémère en 0600 (contient le mot de passe API en clair)
        fd, cfg_path = tempfile.mkstemp(prefix="bf_cfg_", suffix=".json")
        os.write(fd, json.dumps(cfg, ensure_ascii=False).encode("utf-8"))
        os.close(fd)
        os.chmod(cfg_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600

        proc = subprocess.run(
            [str(BINARY), "-json", cfg_path],
            capture_output=True, text=True, timeout=timeout, cwd=str(TOOLS_DIR),
        )

        log_txt = ""
        if log_path and os.path.exists(log_path):
            try:
                log_txt = open(log_path, encoding="utf-8", errors="ignore").read()
            except Exception:
                pass
        raw = "\n".join(x for x in [proc.stdout, proc.stderr, log_txt] if x).strip()

        # Sécurité : ne jamais laisser fuiter un secret dans la sortie renvoyée
        # au client ou écrite dans les logs (le binaire peut écho la config).
        for _sec in (c.get("password"), c.get("login")):
            if _sec:
                raw = raw.replace(_sec, "[masqué]")

        ok = (proc.returncode == 0)
        result = {"ok": ok, "returncode": proc.returncode, "raw": raw}
        if not ok:
            msg = (proc.stderr or proc.stdout or "").strip()
            result["error"] = (msg.splitlines()[-1] if msg
                               else f"Échec BlueFiles (code {proc.returncode})")
        # Extraction best-effort d'un lien / uuid depuis la sortie verbeuse
        mlink = re.search(r"https?://\S+", raw)
        if mlink:
            result["short_link"] = mlink.group(0).rstrip(".,);")
        muuid = re.search(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", raw)
        if muuid:
            result["uuid"] = muuid.group(0)

        if ok:
            logger.info("BlueFiles envoi OK (%d fichier(s), %d destinataire(s))",
                        len(files), len(recs))
        else:
            logger.error("BlueFiles envoi KO (code %s) : %s",
                         proc.returncode, result.get("error"))
        return result

    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "raw": "",
                "error": f"Timeout BlueFiles (> {timeout}s)"}
    except Exception as e:
        logger.exception("BlueFiles cli_sender exception")
        return {"ok": False, "returncode": -1, "raw": "",
                "error": f"{type(e).__name__}: {e}"}
    finally:
        # SUPPRESSION du config (mot de passe en clair) + du log
        for path in (cfg_path, log_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
