"""
plugins/bluefiles/routes.py — v3.5.0-alpha1
============================================
Endpoints API pour le plugin Bluefiles :

  POST /api/v1/bluefiles/send                Envoi sécurisé (multipart)
  GET  /api/v1/bluefiles/envoi/{id}          Détail d'un envoi (statut)
  GET  /api/v1/bluefiles/history             Audit des envois (paginé)
  GET  /api/v1/bluefiles/by_ref              Envois liés à un objet métier
  GET  /api/v1/bluefiles/status              État du plugin (mode dev/live)
  POST /api/v1/bluefiles/webhook             Callback Bluefiles (HMAC vérifié)
"""
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, Request,
    BackgroundTasks,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.api.auth import get_current_user, require_role

from plugins.bluefiles.models import BluefilesEnvoi
from plugins.bluefiles.client import BluefilesClient, current_mode

logger = logging.getLogger("scribe.plugins.bluefiles.routes")
router = APIRouter()


# ── GET /status ──────────────────────────────────────────────────────────────
@router.get("/status")
def plugin_status(user: User = Depends(get_current_user)):
    """État du plugin : mode, configuration, quota.
    Tous les utilisateurs authentifiés peuvent consulter le mode
    (pour décider d'afficher le bouton "Envoi sécurisé").
    """
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return {
        "enabled":  True,
        "mode":     current_mode(),   # "live" | "dev"
        "ready":    True,
        "version":  "3.5.0-alpha1",
    }


# ── POST /send ───────────────────────────────────────────────────────────────
@router.post("/send")
async def send_secure(
    request: Request,
    background_tasks: BackgroundTasks,
    module:    str          = Form(...),
    ref_id:    Optional[int]= Form(None),
    ref_label: Optional[str]= Form(None),
    destinataires: str      = Form(...),   # JSON liste : [{"email":"x@y", "nom":"?"}]
    expiration_days: int    = Form(15),
    password_required: bool = Form(True),
    ar_enabled: bool        = Form(True),
    commentaire: str        = Form(""),
    fichiers:  list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User  = Depends(require_role("soignant", "cellule_crise")),
):
    """Envoi sécurisé d'un ou plusieurs fichiers via Bluefiles.

    Le client (navigateur) POSTe :
      - module     : "transfert" | "communique" | "cellule" | "rex"
      - ref_id     : id de l'objet métier rattaché (transfert #42, etc.)
      - ref_label  : libellé lisible ("Transfert #42 — DUPONT Jean")
      - destinataires : JSON encodé, liste de {email, nom?}
      - fichiers   : multipart, plusieurs files acceptés
      - politique  : expiration, MdP, AR

    Le serveur :
      1. Valide les destinataires (au moins 1 email, max 50)
      2. Pour chaque fichier : hash SHA-256 + taille en streaming
      3. Appelle BluefilesClient.create_envoi → uuid + lien court + MdP
      4. Streame chaque fichier vers Bluefiles (jamais en local)
      5. Finalize l'envoi
      6. Persiste BluefilesEnvoi (audit, sans contenu)
      7. Retourne uuid + lien + MdP destinataires (1× pour affichage)
    """
    import json

    # ── 1. Validation destinataires ─────────────────────────────────────────
    try:
        dest_list = json.loads(destinataires)
        if not isinstance(dest_list, list) or not dest_list:
            raise ValueError("Au moins 1 destinataire requis")
        if len(dest_list) > 50:
            raise ValueError("Maximum 50 destinataires par envoi")
        for d in dest_list:
            if not isinstance(d, dict) or not d.get("email"):
                raise ValueError("Chaque destinataire doit avoir un email")
            email = d["email"].strip().lower()
            if "@" not in email or "." not in email.split("@")[-1]:
                raise ValueError(f"Email invalide : {d.get('email')}")
            d["email"] = email
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Destinataires invalides : {e}")

    if not fichiers:
        raise HTTPException(status_code=400, detail="Au moins 1 fichier requis")

    if module not in ("transfert", "communique", "cellule", "rex", "test"):
        raise HTTPException(status_code=400, detail=f"Module inconnu : {module}")

    # Limites taille (v1 : max 4 Go par envoi, 50 fichiers max)
    MAX_TOTAL_SIZE = 4 * 1024 * 1024 * 1024
    MAX_FILES      = 50
    if len(fichiers) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES} fichiers par envoi")

    # ── 2. Hash + taille de chaque fichier (streaming) ──────────────────────
    fichiers_meta = []
    total_size = 0
    for f in fichiers:
        # On lit le fichier en chunks et hash en streaming
        h = hashlib.sha256()
        size = 0
        # FastAPI UploadFile.file est un SpooledTemporaryFile : pas de copie disque
        while True:
            chunk = await f.read(65536)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
        total_size += size
        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(status_code=413, detail=f"Taille totale > {MAX_TOTAL_SIZE} octets")
        fichiers_meta.append({
            "nom":    f.filename or "(sans nom)",
            "taille": size,
            "mime":   f.content_type or "application/octet-stream",
            "sha256": h.hexdigest(),
        })
        # On rewind le stream pour l'upload qui suit (en mode live)
        await f.seek(0)

    # ── 3. Création de l'envoi côté Bluefiles ──────────────────────────────
    client = BluefilesClient()
    try:
        bf_response = client.create_envoi(
            destinataires     = dest_list,
            fichiers_meta     = fichiers_meta,
            expiration_days   = expiration_days,
            password_required = password_required,
            ar_enabled        = ar_enabled,
            commentaire       = commentaire,
        )
    except Exception as e:
        logger.exception("Bluefiles create_envoi failed")
        raise HTTPException(status_code=502, detail=f"Bluefiles indisponible : {e}")

    bf_uuid    = bf_response["uuid"]
    short_link = bf_response.get("short_link", "")
    upload_url = bf_response.get("upload_url", "")
    expires_iso = bf_response.get("expires_at")
    dest_with_meta = bf_response.get("destinataires", dest_list)

    # ── 4. Upload streamé de chaque fichier vers Bluefiles ─────────────────
    upload_ok = True
    for f in fichiers:
        try:
            ok = client.upload_file(upload_url, f.file, f.filename or "file")
            if not ok:
                upload_ok = False
                break
        except Exception as e:
            logger.exception(f"Bluefiles upload_file({f.filename}) failed")
            upload_ok = False
            break

    # ── 5. Finalize ────────────────────────────────────────────────────────
    finalize_ok = client.finalize_envoi(bf_uuid) if upload_ok else False

    # ── 6. Audit DB ────────────────────────────────────────────────────────
    expires_dt = None
    if expires_iso:
        try:
            expires_dt = datetime.fromisoformat(expires_iso.replace("Z", "+00:00"))
        except ValueError:
            expires_dt = datetime.now(timezone.utc) + timedelta(days=expiration_days)
    else:
        expires_dt = datetime.now(timezone.utc) + timedelta(days=expiration_days)

    # Statut initial
    if not upload_ok:
        statut = "error"
        error_msg = "Upload Bluefiles a échoué"
    elif not finalize_ok:
        statut = "error"
        error_msg = "Finalize Bluefiles a échoué"
    else:
        statut = "delivered"   # En DEV on saute directement à delivered.
        error_msg = None

    # Destinataires audit (sans le MdP — sécurité)
    dest_audit = [
        {
            "email":     d["email"],
            "nom":       d.get("nom", ""),
            "mode_auth": d.get("mode_auth", "password"),
            "statut":    "delivered" if statut == "delivered" else "error",
            "delivered_at": datetime.now(timezone.utc).isoformat() if statut == "delivered" else None,
            "read_at":   None,
        }
        for d in dest_with_meta
    ]

    envoi = BluefilesEnvoi(
        bf_uuid           = bf_uuid,
        mode              = current_mode(),
        module_origine    = module,
        ref_id            = ref_id,
        ref_label         = ref_label,
        auteur_id         = user.id,
        auteur_nom        = user.display_name or user.username,
        auteur_role       = user.role,
        destinataires     = dest_audit,
        fichiers_meta     = fichiers_meta,
        fichiers_total_size = total_size,
        expiration_days   = expiration_days,
        password_required = 1 if password_required else 0,
        ar_enabled        = 1 if ar_enabled else 0,
        commentaire       = commentaire,
        statut            = statut,
        short_link        = short_link,
        uploaded_at       = datetime.now(timezone.utc) if upload_ok else None,
        delivered_at      = datetime.now(timezone.utc) if statut == "delivered" else None,
        expires_at        = expires_dt,
        error_msg         = error_msg,
        webhook_events    = [],
    )
    db.add(envoi)
    db.commit()
    db.refresh(envoi)

    # ── 7. Retour client : MdP destinataires (1 seule fois) + récap ───────
    return {
        "ok":           statut == "delivered",
        "envoi_id":     envoi.id,
        "bf_uuid":      bf_uuid,
        "short_link":   short_link,
        "expires_at":   expires_dt.isoformat() if expires_dt else None,
        "statut":       statut,
        "mode":         current_mode(),
        "destinataires_passwords": [
            {
                "email":     d["email"],
                "mode_auth": d.get("mode_auth", "password"),
                # password présent UNIQUEMENT au retour de send (1 seule fois)
                "password":  d.get("password") if password_required else None,
            }
            for d in dest_with_meta
        ],
        "error":        error_msg,
    }


# ── GET /envoi/{id} ──────────────────────────────────────────────────────────
@router.get("/envoi/{envoi_id}")
def get_envoi(
    envoi_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Détail d'un envoi (statut, destinataires, fichiers). PAS le contenu."""
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    envoi = db.query(BluefilesEnvoi).filter_by(id=envoi_id).first()
    if not envoi:
        raise HTTPException(status_code=404, detail="Envoi introuvable")
    # Restriction : seul l'auteur ou un admin peut consulter
    if user.role != "admin" and envoi.auteur_id != user.id:
        raise HTTPException(status_code=403, detail="Accès interdit")
    return envoi.to_dict()


# ── GET /by_ref ──────────────────────────────────────────────────────────────
@router.get("/by_ref")
def list_envois_by_ref(
    module: str,
    ref_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Liste les envois liés à un objet métier (ex: transfert #42).
    Sert à afficher la section "Dossiers transmis" dans la fiche transfert.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    rows = (db.query(BluefilesEnvoi)
              .filter_by(module_origine=module, ref_id=ref_id)
              .order_by(BluefilesEnvoi.created_at.desc())
              .all())
    return {"envois": [r.to_dict() for r in rows]}


# ── GET /history ─────────────────────────────────────────────────────────────
@router.get("/history")
def list_envois(
    limit:  int = 50,
    offset: int = 0,
    module: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Historique paginé des envois. Admin voit tout, user voit ses envois."""
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    limit = max(1, min(limit, 100))
    q = db.query(BluefilesEnvoi)
    if user.role != "admin":
        q = q.filter(BluefilesEnvoi.auteur_id == user.id)
    if module:
        q = q.filter(BluefilesEnvoi.module_origine == module)
    total = q.count()
    rows  = (q.order_by(BluefilesEnvoi.created_at.desc())
              .offset(offset).limit(limit).all())
    return {
        "total":  total,
        "offset": offset,
        "limit":  limit,
        "envois": [r.to_dict(include_meta=False) for r in rows],
    }


# ── POST /webhook ────────────────────────────────────────────────────────────
@router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Callback de Bluefiles : événements delivered/read/expired/error.
    Vérifie la signature HMAC avant traitement.

    Format attendu (approximation, à ajuster avec doc Bluefiles) :
      {
        "event": "envoi.read",
        "envoi_uuid": "...",
        "recipient_email": "...",
        "timestamp": "..."
      }
    """
    import json
    body = await request.body()
    signature = request.headers.get("X-Bluefiles-Signature", "")

    client = BluefilesClient()
    if not client.verify_webhook(body, signature):
        logger.warning("Webhook Bluefiles : signature HMAC invalide — rejeté")
        raise HTTPException(status_code=401, detail="Signature invalide")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Body JSON invalide")

    event_type    = event.get("event", "")
    uuid          = event.get("envoi_uuid", "")
    recipient     = event.get("recipient_email", "").lower()
    ts_iso        = event.get("timestamp", "")

    envoi = db.query(BluefilesEnvoi).filter_by(bf_uuid=uuid).first()
    if not envoi:
        # Webhook pour un envoi qu'on ne connaît pas (autre instance ?)
        # On accepte mais on ne traite pas — pas d'erreur, pour éviter retry inutile.
        return {"ok": True, "msg": "Envoi inconnu localement"}

    # Append au log audit
    events = envoi.webhook_events or []
    events.append({
        "event":     event_type,
        "recipient": recipient,
        "timestamp": ts_iso,
        "received_at": datetime.now(timezone.utc).isoformat(),
    })
    envoi.webhook_events = events

    # Mise à jour du statut destinataire concerné
    dest_list = envoi.destinataires or []
    for d in dest_list:
        if d.get("email", "").lower() == recipient:
            if event_type == "envoi.delivered":
                d["statut"]       = "delivered"
                d["delivered_at"] = ts_iso
            elif event_type == "envoi.read":
                d["statut"]  = "read"
                d["read_at"] = ts_iso
            elif event_type == "envoi.expired":
                d["statut"] = "expired"
            elif event_type == "envoi.error":
                d["statut"] = "error"
            break
    envoi.destinataires = dest_list

    # Maj statut global :
    # - "read" si TOUS lus
    # - "delivered" sinon
    # - "expired" si TOUS expirés
    statuts = [d.get("statut", "pending") for d in dest_list]
    if statuts and all(s == "read" for s in statuts):
        envoi.statut = "read"
    elif statuts and all(s == "expired" for s in statuts):
        envoi.statut = "expired"
    elif "error" in statuts:
        envoi.statut = "error"

    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION ADMIN — v3000h41
# ──────────────────────────────────────────────────────────────────────────────
# Permet d'éditer l'intégration Bluefiles depuis l'admin (clic sur le plugin),
# sans avoir à exporter des variables d'environnement SCRIBE_BLUEFILES_* dans
# lancer_scribe.sh. La config en DB a priorité ; les env vars restent un repli.
#
# Sécurité :
#   - Admin requis (require_admin).
#   - api_key / webhook_secret JAMAIS renvoyés en clair : aperçu masqué + booléen.
#   - Écrire une chaîne vide sur api_url/account => repli sur l'env var.
#   - Effacer une clé secrète => champ dédié clear_* (évite l'effacement
#     accidentel quand l'admin laisse le champ masqué inchangé).
# ══════════════════════════════════════════════════════════════════════════════
from pydantic import BaseModel as _BaseModel
from app.api.auth import require_admin
from plugins.bluefiles.client import get_config, _ENV_DEFAULTS
from plugins.bluefiles.models import BluefilesConfig


def _mask_secret(val: str) -> str:
    """Aperçu masqué : '••••••1a2b' (4 derniers car.) ou '' si vide."""
    if not val:
        return ""
    if len(val) <= 4:
        return "•" * len(val)
    return "•" * 6 + val[-4:]


def _source_of(field: str, row) -> str:
    """Indique d'où vient la valeur effective : 'db' | 'env' | 'none'."""
    db_val = (getattr(row, field, "") or "").strip() if row else ""
    if db_val:
        return "db"
    if (_ENV_DEFAULTS.get(field) or "").strip():
        return "env"
    return "none"


class BluefilesConfigIn(_BaseModel):
    api_url:            Optional[str] = None
    account:            Optional[str] = None
    api_key:            Optional[str] = None   # non vide => remplace
    webhook_secret:    Optional[str] = None    # non vide => remplace
    clear_api_key:      Optional[bool] = False
    clear_webhook_secret: Optional[bool] = False


@router.get("/admin/config")
def get_bluefiles_config(admin: User = Depends(require_admin),
                         db: Session = Depends(get_db)):
    """Config courante (secrets masqués) + source effective de chaque champ."""
    row = db.query(BluefilesConfig).filter_by(id=1).first()
    eff = get_config()
    return {
        "api_url":             eff["api_url"],
        "account":             eff["account"],
        "api_key_set":         bool(eff["api_key"]),
        "api_key_preview":     _mask_secret(eff["api_key"]),
        "webhook_secret_set":  bool(eff["webhook_secret"]),
        "webhook_secret_preview": _mask_secret(eff["webhook_secret"]),
        "mode":                current_mode(),
        "sources": {
            "api_url":        _source_of("api_url", row),
            "account":        _source_of("account", row),
            "api_key":        _source_of("api_key", row),
            "webhook_secret": _source_of("webhook_secret", row),
        },
        "updated_at": row.updated_at.isoformat() if (row and row.updated_at) else None,
        "updated_by": row.updated_by if row else None,
    }


@router.post("/admin/config")
def save_bluefiles_config(body: BluefilesConfigIn,
                          admin: User = Depends(require_admin),
                          db: Session = Depends(get_db)):
    """Enregistre la config Bluefiles (singleton id=1)."""
    row = db.query(BluefilesConfig).filter_by(id=1).first()
    if not row:
        row = BluefilesConfig(id=1)
        db.add(row)

    # api_url / account : la valeur fournie remplace (vide => repli env)
    if body.api_url is not None:
        row.api_url = body.api_url.strip()
    if body.account is not None:
        row.account = body.account.strip()

    # api_key : effacement explicite, sinon remplacement si non vide
    if body.clear_api_key:
        row.api_key = ""
    elif body.api_key and body.api_key.strip():
        row.api_key = body.api_key.strip()

    # webhook_secret : idem
    if body.clear_webhook_secret:
        row.webhook_secret = ""
    elif body.webhook_secret and body.webhook_secret.strip():
        row.webhook_secret = body.webhook_secret.strip()

    row.updated_by = admin.username
    db.commit()

    # Journalisation main courante (sans secret)
    try:
        from app.api.v140 import _log_mc
        _log_mc(db, admin, "ADMIN", "CONFIG BLUEFILES",
                f"Configuration Bluefiles mise à jour par {admin.username} "
                f"(mode={current_mode()})", niveau="INFO")
    except Exception:
        pass

    return {"ok": True, "mode": current_mode()}


@router.post("/admin/config/test")
def test_bluefiles_config(admin: User = Depends(require_admin)):
    """Test léger de la configuration : en mode DEV, indique simplement que le
    connecteur fonctionnera en simulation. En mode LIVE, tente un GET de santé
    sur l'API (best-effort, sans exposer de secret).
    """
    cfg = get_config()
    if not (cfg["api_key"] and cfg["api_url"] and cfg["account"]):
        return {"ok": True, "mode": "dev",
                "detail": "Mode DEV : aucune clé configurée, envois simulés (aucun appel réseau)."}
    import httpx
    try:
        with httpx.Client(timeout=10.0) as cli:
            r = cli.get(f"{cfg['api_url'].rstrip('/')}/health",
                        headers={"Authorization": f"Bearer {cfg['api_key']}",
                                 "X-Account": cfg["account"],
                                 "Accept": "application/json"})
        reachable = r.status_code < 500
        return {"ok": reachable, "mode": "live", "status_code": r.status_code,
                "detail": ("API joignable." if reachable
                           else f"API en erreur (HTTP {r.status_code}).")}
    except Exception as e:
        return {"ok": False, "mode": "live",
                "detail": f"Connexion impossible : {type(e).__name__}."}
