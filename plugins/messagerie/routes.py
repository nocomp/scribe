"""
plugins/messagerie/routes.py — v3.6.0-alpha1 (Phase 1)
========================================================
Routes API REST du plugin messagerie refondu.

Endpoints :
  GET    /folders                      arbo dossiers (standards virtuels + persos)
  POST   /folders                      créer dossier perso
  PATCH  /folders/{id}                 renommer / déplacer
  DELETE /folders/{id}                 supprimer (msgs → Inbox)

  GET    /messages                     liste paginée + filtres
  GET    /messages/{id}                détail
  POST   /messages                     nouveau message (multipart PJ)
  POST   /messages/{id}/reply          répondre
  POST   /messages/{id}/reply-all      répondre à tous
  POST   /messages/{id}/forward        transférer
  PATCH  /messages/{id}                déplacer/marquer lu/important
  DELETE /messages/{id}                soft delete → corbeille
  POST   /messages/{id}/restore        sortir de la corbeille
  DELETE /messages/{id}/permanent      suppression définitive

  GET    /attachments/{id}             télécharger PJ locale
  DELETE /attachments/{id}             supprimer PJ (si auteur)

  POST   /messages/{id}/lire           [LEGACY compat]  marquer lu
  GET    /non-lus                      [LEGACY compat]  count
"""
import os
import uuid
import shutil
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, text
from pydantic import BaseModel

from app.database import get_db
from app.models import User
from app.api.auth import get_current_user, require_role

from plugins.messagerie.models import Message, Folder, MessageAttachment

logger = logging.getLogger("scribe.plugins.messagerie")
router = APIRouter()


# ── Configuration stockage PJ ────────────────────────────────────────────────
UPLOADS_BASE = Path(os.getenv("SCRIBE_UPLOADS_DIR", "uploads")) / "messages"
MAX_ATTACHMENT_SIZE       = 10 * 1024 * 1024      # 10 Mo par PJ
MAX_TOTAL_ATTACHMENT_SIZE = 25 * 1024 * 1024      # 25 Mo total par message
MAX_ATTACHMENTS_PER_MSG   = 10


# ── Utilitaires ──────────────────────────────────────────────────────────────
def _ensure_uploads_dir(message_id: int) -> Path:
    p = UPLOADS_BASE / str(message_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _user_inbox_predicate(user_id: int):
    """Construit le critère SQL pour les messages reçus par cet user.
    Comme `destinataires` est une colonne JSON (stockée TEXT sur SQLite),
    on fait une recherche par cast en String + LIKE pour portabilité maximale
    (SQLite/PostgreSQL/MySQL).
    Pour les volumes hospitaliers raisonnables c'est OK ; si volume + performance
    critique, migrer vers une table de jointure dédiée.
    """
    from sqlalchemy import cast, String
    needle = f'"type": "user", "value": {user_id}'   # match JSON dump
    # Fallback si le JSON est sérialisé sans espace après les virgules
    needle_compact = f'"type":"user","value":{user_id}'
    dest_str = cast(Message.destinataires, String)
    return or_(
        dest_str.like(f"%{needle}%"),
        dest_str.like(f"%{needle_compact}%"),
    )


def _msg_to_display(m: Message, db: Session, viewer_id: int) -> dict:
    """Enrichit le dict avec un libellé d'affichage adapté au viewer."""
    d = m.to_dict()
    # is_inbox : true si je suis dans destinataires (= reçu)
    is_inbox = False
    for dest in (m.destinataires or []):
        if dest.get("type") == "user" and int(dest.get("value", 0) or 0) == viewer_id:
            is_inbox = True
            break
    d["is_inbox"]   = is_inbox
    d["is_sent"]    = (m.expediteur_id == viewer_id)
    # Résumé de l'aperçu (premiers 120 caractères)
    d["preview"]    = (m.contenu or "")[:120].replace("\n", " ").strip()
    return d


def _gen_thread_id() -> str:
    return uuid.uuid4().hex


# ── Pydantic schemas ─────────────────────────────────────────────────────────
class FolderIn(BaseModel):
    nom:        str
    canal:      str = "interne"
    parent_id:  Optional[int] = None
    color_hex:  Optional[str] = None
    icon:       Optional[str] = "📁"


class FolderUpdate(BaseModel):
    nom:        Optional[str] = None
    parent_id:  Optional[int] = None
    ordre:      Optional[int] = None
    color_hex:  Optional[str] = None
    icon:       Optional[str] = None


class MessagePatch(BaseModel):
    """Patch d'un message : marquer lu, important, déplacer dossier."""
    lu:             Optional[bool] = None
    flag_important: Optional[bool] = None
    folder_id:      Optional[int]  = None  # None pour décrocher du dossier
    contenu_redacted: Optional[bool] = None  # caviarder son propre msg


# ─────────────────────────────────────────────────────────────────────────────
# DOSSIERS
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/folders")
def list_folders(
    canal: Optional[str] = Query(None),
    db:    Session = Depends(get_db),
    user:  User = Depends(get_current_user),
):
    """Liste les dossiers PERSONNELS de l'utilisateur courant.

    Les dossiers STANDARDS (inbox/sent/drafts/trash/important) sont VIRTUELS
    et calculés côté frontend depuis les compteurs renvoyés par /messages.
    """
    if not user:
        raise HTTPException(401)
    q = db.query(Folder).filter(Folder.user_id == user.id)
    if canal:
        q = q.filter(Folder.canal == canal)
    rows = q.order_by(Folder.canal, Folder.ordre, Folder.nom).all()
    return {"folders": [f.to_dict() for f in rows]}


@router.post("/folders")
def create_folder(
    body: FolderIn,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)
    if body.canal not in ("interne", "mail", "sms", "all"):
        raise HTTPException(400, "Canal invalide")
    if len(body.nom) > 100 or not body.nom.strip():
        raise HTTPException(400, "Nom de dossier invalide")
    f = Folder(
        user_id   = user.id,
        canal     = body.canal,
        nom       = body.nom.strip(),
        parent_id = body.parent_id,
        color_hex = body.color_hex,
        icon      = body.icon or "📁",
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f.to_dict()


@router.patch("/folders/{folder_id}")
def update_folder(
    folder_id: int,
    body: FolderUpdate,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)
    f = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not f:
        raise HTTPException(404, "Dossier introuvable")
    if body.nom is not None and body.nom.strip():
        f.nom = body.nom.strip()
    if body.parent_id is not None:
        f.parent_id = body.parent_id or None
    if body.ordre is not None:
        f.ordre = body.ordre
    if body.color_hex is not None:
        f.color_hex = body.color_hex or None
    if body.icon is not None:
        f.icon = body.icon or "📁"
    db.commit()
    db.refresh(f)
    return f.to_dict()


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supprime un dossier. Les messages dedans deviennent décrochés (Inbox)."""
    if not user:
        raise HTTPException(401)
    f = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not f:
        raise HTTPException(404, "Dossier introuvable")
    # Décrocher les messages
    db.query(Message).filter(Message.folder_id == folder_id).update({"folder_id": None})
    db.delete(f)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES — Liste & Détail
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/messages")
def list_messages(
    canal:    str = Query("interne"),
    box:      str = Query("inbox"),   # inbox | sent | drafts | trash | important | folder
    folder_id: Optional[int] = Query(None),
    search:   Optional[str]  = Query(None),
    limit:    int = Query(50, ge=1, le=200),
    offset:   int = Query(0,  ge=0),
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Liste paginée des messages selon la boîte virtuelle ou un dossier perso.

    Boîtes virtuelles :
      - inbox     : reçus, non supprimés, non brouillons
      - sent      : envoyés (expediteur_id = moi), statut sent, non supprimés
      - drafts    : statut draft, expediteur_id = moi
      - trash     : deleted_at NOT NULL
      - important : flag_important, non supprimés
      - folder    : nécessite folder_id
    """
    if not user:
        raise HTTPException(401)

    q = db.query(Message).filter(Message.canal == canal)

    if box == "trash":
        q = q.filter(Message.deleted_at.isnot(None))
        q = q.filter(or_(
            Message.expediteur_id == user.id,
            _user_inbox_predicate(user.id),
        ))
    else:
        # Tous les autres : exclure la corbeille
        q = q.filter(Message.deleted_at.is_(None))

    if box == "inbox":
        q = q.filter(Message.statut != "draft")
        q = q.filter(_user_inbox_predicate(user.id))
    elif box == "sent":
        q = q.filter(Message.expediteur_id == user.id, Message.statut == "sent")
    elif box == "drafts":
        q = q.filter(Message.expediteur_id == user.id, Message.statut == "draft")
    elif box == "important":
        q = q.filter(Message.flag_important == True)
        q = q.filter(or_(
            Message.expediteur_id == user.id,
            _user_inbox_predicate(user.id),
        ))
    elif box == "folder":
        if not folder_id:
            raise HTTPException(400, "folder_id requis pour box=folder")
        # Vérifier que le dossier appartient bien à l'user
        f = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
        if not f:
            raise HTTPException(404, "Dossier introuvable")
        q = q.filter(Message.folder_id == folder_id)
    elif box == "trash":
        pass  # déjà filtré ci-dessus
    else:
        raise HTTPException(400, f"box inconnue : {box}")

    # Recherche simple (LIKE)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Message.sujet.ilike(like),
            Message.contenu.ilike(like),
            Message.expediteur_nom.ilike(like),
        ))

    total = q.count()
    rows  = q.order_by(Message.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total":   total,
        "limit":   limit,
        "offset":  offset,
        "canal":   canal,
        "box":     box,
        "messages": [_msg_to_display(m, db, user.id) for m in rows],
    }


@router.get("/messages/counters")
def get_counters(
    canal: str = Query("interne"),
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Compteurs par boîte (badge dans la sidebar)."""
    if not user:
        raise HTTPException(401)
    # Tous les compteurs hors corbeille
    base = db.query(Message).filter(
        Message.canal == canal,
        Message.deleted_at.is_(None),
    )

    inbox = base.filter(
        Message.statut != "draft",
        _user_inbox_predicate(user.id),
    )
    inbox_unread = inbox.filter(Message.lu == False).count()
    inbox_total  = inbox.count()
    sent   = base.filter(Message.expediteur_id == user.id, Message.statut == "sent").count()
    drafts = base.filter(Message.expediteur_id == user.id, Message.statut == "draft").count()
    important = base.filter(Message.flag_important == True).filter(or_(
        Message.expediteur_id == user.id,
        _user_inbox_predicate(user.id),
    )).count()
    trash = db.query(Message).filter(
        Message.canal == canal,
        Message.deleted_at.isnot(None),
        or_(Message.expediteur_id == user.id, _user_inbox_predicate(user.id)),
    ).count()

    # Par dossier perso
    folders = db.query(Folder).filter(
        Folder.user_id == user.id,
        Folder.canal == canal,
    ).all()
    folder_counters = {}
    for f in folders:
        folder_counters[f.id] = base.filter(Message.folder_id == f.id).count()

    return {
        "canal":  canal,
        "inbox":  inbox_total,
        "inbox_unread": inbox_unread,
        "sent":   sent,
        "drafts": drafts,
        "important": important,
        "trash":  trash,
        "folders": folder_counters,
    }


@router.get("/messages/{msg_id}")
def get_message(
    msg_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)
    m = db.query(Message).filter(Message.id == msg_id).first()
    if not m:
        raise HTTPException(404, "Message introuvable")
    # ACL : doit être expéditeur ou un des destinataires
    if not _can_access(m, user.id):
        raise HTTPException(403, "Accès interdit")
    # Joindre les PJ
    atts = db.query(MessageAttachment).filter(MessageAttachment.message_id == m.id).all()
    d = _msg_to_display(m, db, user.id)
    d["attachments"] = [a.to_dict() for a in atts]
    return d


def _can_access(m: Message, user_id: int) -> bool:
    if m.expediteur_id == user_id:
        return True
    for dest in (m.destinataires or []):
        if dest.get("type") == "user" and int(dest.get("value", 0) or 0) == user_id:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES — Création / Réponse / Transfert
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/messages")
async def create_message(
    request: Request,
    canal:     str = Form("interne"),
    sujet:     str = Form(""),
    contenu:   str = Form(""),
    destinataires_json: str = Form("[]"),   # JSON list[{type,value}]
    reply_to_id: Optional[int] = Form(None),
    draft:     bool = Form(False),
    fichiers:  list[UploadFile] = File([]),
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Crée un message (envoyé ou brouillon) + PJ optionnelles."""
    if not user:
        raise HTTPException(401)

    # h77 — Canaux activés : interne + mail (SMTP). SMS reste hors messagerie.
    if canal not in ("interne", "mail"):
        raise HTTPException(400, "Canal non supporté (interne ou mail).")

    # Valider destinataires
    import json
    try:
        dest_list = json.loads(destinataires_json)
        if not isinstance(dest_list, list):
            raise ValueError("doit être une liste")
    except Exception as e:
        raise HTTPException(400, f"destinataires_json invalide : {e}")

    # Phase 1 : ne garder que les destinataires "user"
    dest_clean = []
    for d in dest_list:
        if not isinstance(d, dict):
            continue
        if d.get("type") == "user":
            try:
                uid = int(d.get("value"))
            except (TypeError, ValueError):
                continue
            target = db.query(User).filter(User.id == uid, User.active == True).first()
            if not target:
                continue
            dest_clean.append({
                "type":    "user",
                "value":   uid,
                "display": target.display_name or target.username,
            })
        elif d.get("type") == "supervision":
            # v3000h48 — destinataire « supervision » conservé : le message est
            # écrit dans Envoyés (avec PJ) puis livré au collecteur (même plugin).
            dest_clean.append({"type": "supervision", "value": "SUPERVISION", "display": "Supervision"})
        elif d.get("type") == "email":
            # h77 — Adresse e-mail saisie librement (canal mail).
            import re as _re
            _addr = str(d.get("value") or "").strip()
            if _addr and _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", _addr):
                dest_clean.append({"type": "email", "value": _addr, "display": _addr})
        elif d.get("type") == "agent_federe":
            # h69 — destinataire nominatif d'une AUTRE instance (sigle + username).
            # Conservé tel quel ; livré via le relais collecteur après commit.
            _etab = str(d.get("etab") or "").upper()
            _uname = str(d.get("value") or "").strip()
            if _etab and _uname:
                dest_clean.append({"type": "agent_federe", "value": _uname, "etab": _etab,
                                   "display": d.get("display") or (_uname + "@" + _etab)})
    if not draft and not dest_clean:
        raise HTTPException(400, "Au moins un destinataire requis")

    # Threading
    thread_id = ""
    parent = None
    if reply_to_id:
        parent = db.query(Message).filter(Message.id == reply_to_id).first()
        if parent:
            thread_id = parent.thread_id or _gen_thread_id()
    if not thread_id:
        thread_id = _gen_thread_id()

    # PJ : validation préalable des tailles
    total_size = 0
    if fichiers:
        if len(fichiers) > MAX_ATTACHMENTS_PER_MSG:
            raise HTTPException(400, f"Maximum {MAX_ATTACHMENTS_PER_MSG} PJ par message")
        for f in fichiers:
            # On ne peut pas connaître la taille sans lire — on lira au moment de stocker
            pass

    msg = Message(
        canal           = canal,
        direction       = "out",
        expediteur_id   = user.id,
        expediteur_nom  = user.display_name or user.username,
        destinataires   = dest_clean,
        sujet           = (sujet or "").strip()[:500],
        contenu         = contenu or "",
        contenu_format  = "plain",
        reply_to_id     = reply_to_id if parent else None,
        thread_id       = thread_id,
        statut          = "draft" if draft else "sent",
        sent_at         = None if draft else datetime.now(timezone.utc),
    )
    db.add(msg)
    db.flush()  # pour avoir msg.id

    # Stocker les PJ (uniquement si pas brouillon, ou même en brouillon ?)
    # Décision : en brouillon on stocke aussi (l'user veut récupérer son brouillon avec PJ).
    saved_count = 0
    if fichiers:
        target_dir = _ensure_uploads_dir(msg.id)
        for upload in fichiers:
            if saved_count >= MAX_ATTACHMENTS_PER_MSG:
                break
            try:
                # Lire et hasher en stream
                safe_name = _safe_filename(upload.filename or f"file_{saved_count}")
                dest_path = target_dir / safe_name
                # Éviter collisions
                idx = 1
                while dest_path.exists():
                    stem = safe_name.rsplit(".", 1)
                    if len(stem) == 2:
                        dest_path = target_dir / f"{stem[0]}_{idx}.{stem[1]}"
                    else:
                        dest_path = target_dir / f"{safe_name}_{idx}"
                    idx += 1
                h = hashlib.sha256()
                size = 0
                with open(dest_path, "wb") as out:
                    while True:
                        chunk = await upload.read(65536)
                        if not chunk:
                            break
                        if size + len(chunk) > MAX_ATTACHMENT_SIZE:
                            out.close()
                            try: dest_path.unlink()
                            except OSError: pass
                            raise HTTPException(413, f"PJ > {MAX_ATTACHMENT_SIZE} octets : {upload.filename}")
                        if total_size + len(chunk) > MAX_TOTAL_ATTACHMENT_SIZE:
                            out.close()
                            try: dest_path.unlink()
                            except OSError: pass
                            raise HTTPException(413, f"Total PJ > {MAX_TOTAL_ATTACHMENT_SIZE} octets")
                        h.update(chunk)
                        out.write(chunk)
                        size += len(chunk)
                        total_size += len(chunk)
                # Insert attachment
                att = MessageAttachment(
                    message_id   = msg.id,
                    kind         = "local",
                    nom          = upload.filename or safe_name,
                    taille       = size,
                    mime         = upload.content_type or "application/octet-stream",
                    sha256       = h.hexdigest(),
                    storage_path = str(dest_path),
                )
                db.add(att)
                saved_count += 1
            except HTTPException:
                raise
            except Exception as e:
                logger.exception(f"Erreur stockage PJ {upload.filename}")
                raise HTTPException(500, f"Erreur stockage PJ : {e}")

    msg.attachments_count = saved_count
    db.commit()
    db.refresh(msg)

    # v3000h48 — Livraison inter-nœud : si un destinataire « supervision » est
    # présent, on livre le message + PJ au collecteur (qui fait tourner le même
    # plugin). Best-effort : un échec ne casse jamais l'envoi/stockage local.
    if not draft:
        try:
            if any(isinstance(d, dict) and d.get("type") == "supervision"
                   for d in (msg.destinataires or [])):
                await _deliver_to_supervision(msg, db)
        except Exception:
            logger.warning("[messagerie] livraison supervision échouée (message conservé en local)", exc_info=True)
        # h69 — Livraison des destinataires nominatifs d'autres établissements.
        for d in (msg.destinataires or []):
            if isinstance(d, dict) and d.get("type") == "agent_federe":
                try:
                    await _deliver_to_agent_federe(msg, d.get("etab"), d.get("value"))
                except Exception:
                    logger.warning("[messagerie] livraison agent fédéré échouée (message conservé en local)", exc_info=True)
        # h77 — Livraison MAIL : envoi SMTP aux destinataires e-mail / utilisateurs.
        if msg.canal == "mail":
            try:
                await _deliver_mail(msg, db)
            except Exception:
                logger.warning("[messagerie] envoi mail échoué (message conservé en local)", exc_info=True)

    return _msg_to_display(msg, db, user.id)


async def _deliver_mail(msg, db):
    """h77 — Envoie le message par e-mail (SMTP) aux destinataires de type
    'email' (adresse libre) et 'user' (e-mail résolu depuis le compte). Réutilise
    le canal mail configuré côté notifications (MailBackend, transport déjà validé).
    Best-effort : un échec n'altère jamais l'enregistrement local du message."""
    from plugins.notifications.models import NotifChannel
    from plugins.notifications.backends import BACKENDS, NotifPayload
    from plugins.notifications.dispatcher import _apply_central_config
    import json as _j
    ch = (db.query(NotifChannel)
            .filter(NotifChannel.kind == "mail", NotifChannel.enabled == True)  # noqa: E712
            .first())
    if not ch:
        logger.warning("[messagerie] canal mail non activé côté serveur — envoi mail ignoré")
        return
    cfg = _apply_central_config("mail", _j.loads(ch.config_json or "{}"))
    backend_cls = BACKENDS.get("mail")
    if not backend_cls:
        return
    backend = backend_cls(cfg)
    if not backend.is_configured():
        logger.warning("[messagerie] canal mail mal configuré — envoi mail ignoré")
        return
    emails = []
    for d in (msg.destinataires or []):
        if not isinstance(d, dict):
            continue
        if d.get("type") == "email":
            a = str(d.get("value") or "").strip()
            if a:
                emails.append(a)
        elif d.get("type") == "user":
            try:
                u = db.query(User).filter(User.id == int(d.get("value"))).first()
                if u and u.email:
                    emails.append(u.email)
            except (TypeError, ValueError):
                pass
    emails = list(dict.fromkeys(emails))   # dédup, ordre préservé
    if not emails:
        logger.warning("[messagerie] aucun e-mail résolu pour le message #%s", msg.id)
        return
    payload = NotifPayload(event_type="messagerie_mail",
                           title=(msg.sujet or "(sans objet)"),
                           body=(msg.contenu or ""), urgency=2, context={})
    # h78 — Charger les PJ locales du message pour les joindre au mail.
    atts = []
    try:
        rows = (db.query(MessageAttachment)
                  .filter(MessageAttachment.message_id == msg.id,
                          MessageAttachment.kind == "local").all())
        for a in rows:
            try:
                pth = Path(a.storage_path)
                if pth.exists():
                    atts.append((a.nom or pth.name, pth.read_bytes(),
                                 a.mime or "application/octet-stream"))
            except Exception:
                pass
    except Exception:
        atts = []
    for addr in emails:
        try:
            await backend.send(payload, addr, attachments=atts)
        except Exception:
            logger.warning("[messagerie] échec envoi mail à %s (message #%s)", addr, msg.id, exc_info=True)


async def _deliver_to_supervision(msg, db):
    """Livre un message + ses PJ au collecteur via /api/v1/messagerie/ingest."""
    # v3000h51 — On lit la config fédération DIRECTEMENT dans le XML (même source
    # que federation._load : SCRIBE_CONFIG_FILE, sinon config.xml), SANS importer
    # app.api.federation — dont l'import isolé plante (NameError 'Depends', car ce
    # module utilise Depends sans l'importer). On ne dépend donc plus de ce module.
    import os as _os, xml.etree.ElementTree as _ET
    collecteur_url, sigle, nom = "", "", "Instance"
    cfg_path = _os.environ.get("SCRIBE_CONFIG_FILE", "config.xml")
    try:
        if _os.path.exists(cfg_path):
            root = _ET.parse(cfg_path).getroot()
            fed = root.find("federation")
            etab = root.find("etablissement")
            def _tx(parent, tag, d=""):
                if parent is None:
                    return d
                el = parent.find(tag)
                return el.text.strip() if (el is not None and el.text) else d
            collecteur_url = _tx(fed, "collecteur_url")
            sigle = _tx(etab, "sigle")
            nom = _tx(etab, "nom", "Instance")
    except Exception as e:
        logger.warning("[messagerie] livraison supervision : lecture %s échouée (%s)", cfg_path, e)
    if not collecteur_url:
        logger.warning("[messagerie] livraison supervision IGNORÉE : collecteur_url introuvable dans %s", cfg_path)
        return
    base = collecteur_url.replace("/api/push", "")
    url = base + "/api/v1/messagerie/ingest"
    data = {
        "origin_sigle": sigle or "",
        "origin_nom":   nom or sigle or "Instance",
        "sujet":        msg.sujet or "",
        "contenu":      msg.contenu or "",
        "source_uuid":  f"{sigle or 'ETB'}-{msg.id}",
        "recipient_username": "supervision",
        "node_token":   os.getenv("SCRIBE_NODE_TOKEN", ""),
    }
    files = []
    try:
        atts = db.query(MessageAttachment).filter(
            MessageAttachment.message_id == msg.id,
            MessageAttachment.kind == "local",
        ).all()
        for a in atts:
            try:
                p = Path(a.storage_path)
                if p.exists():
                    files.append(("fichiers", (a.nom or p.name, p.read_bytes(),
                                               a.mime or "application/octet-stream")))
            except Exception:
                pass
    except Exception:
        pass
    logger.info("[messagerie] livraison supervision : POST %s (%s PJ)", url, len(files))
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20, verify=False) as cli:
            r = await cli.post(url, data=data, files=files or None)
            logger.info("[messagerie] livraison supervision → HTTP %s : %s", r.status_code, (r.text or "")[:200])
    except Exception as e:
        logger.warning("[messagerie] livraison supervision ÉCHEC réseau vers %s : %s", url, e)


def _read_fed_config():
    """Lit (collecteur_url, token, sigle, nom) depuis le XML de config — sans
    importer app.api.federation (qui plante en import isolé)."""
    import os as _os, xml.etree.ElementTree as _ET
    collecteur_url, token, sigle, nom = "", "", "", "Instance"
    cfg_path = _os.environ.get("SCRIBE_CONFIG_FILE", "config.xml")
    try:
        if _os.path.exists(cfg_path):
            root = _ET.parse(cfg_path).getroot()
            fed = root.find("federation"); etab = root.find("etablissement")
            def _tx(p, t, d=""):
                if p is None:
                    return d
                el = p.find(t)
                return el.text.strip() if (el is not None and el.text) else d
            collecteur_url = _tx(fed, "collecteur_url")
            token = _tx(fed, "token")
            sigle = _tx(etab, "sigle")
            nom = _tx(etab, "nom", "Instance")
    except Exception as e:
        logger.warning("[messagerie] lecture config fédération échouée : %s", e)
    return collecteur_url, token, sigle, nom


@router.get("/correspondants-federes")
async def correspondants_federes(user: User = Depends(get_current_user)):
    """Annuaire des agents des AUTRES établissements fédérés, groupé par
    établissement (via le collecteur /api/annuaire). Annuaire professionnel
    uniquement — aucune donnée patient. Sert au sélecteur de destinataires
    inter-établissements de la messagerie."""
    if not user:
        raise HTTPException(401)
    import httpx
    collecteur_url, _token, my_sigle, _nom = _read_fed_config()
    my_sigle = (my_sigle or "").upper()
    if not collecteur_url:
        return {"etablissements": []}
    base = collecteur_url.replace("/api/push", "")
    out = []
    try:
        async with httpx.AsyncClient(timeout=8, verify=False) as cli:
            r = await cli.get(base + "/api/annuaire")
            if r.status_code == 200:
                for etb in (r.json() or []):
                    sig = (etb.get("sigle") or "").upper()
                    if not sig or sig == my_sigle or etb.get("unavailable"):
                        continue   # on n'expose pas l'annuaire local (déjà dispo)
                    agents = [{"username": c.get("username"),
                               "display_name": c.get("display_name") or c.get("username"),
                               "role": c.get("role") or ""}
                              for c in (etb.get("contacts") or []) if c.get("username")]
                    if agents:
                        out.append({"sigle": sig, "nom": etb.get("nom") or sig,
                                    "agents": agents})
    except Exception as e:
        logger.warning("[messagerie] annuaire fédéré injoignable : %s", e)
    return {"etablissements": out}


async def _deliver_to_agent_federe(msg, target_sigle, recipient_username):
    """Relaie un message vers un agent nominatif d'une AUTRE instance, via le
    relais collecteur /api/coll/msg-to-instance (authentifié par le token de
    fédération). Best-effort : un échec ne casse jamais le stockage local."""
    import httpx
    collecteur_url, token, sigle, nom = _read_fed_config()
    if not collecteur_url or not token:
        logger.warning("[messagerie] agent fédéré IGNORÉ : collecteur_url/token manquant")
        return
    base = collecteur_url.replace("/api/push", "")
    url = base + "/api/coll/msg-to-instance"
    data = {
        "target_sigle":       (target_sigle or "").upper(),
        "recipient_username": recipient_username or "",
        "origin_sigle":       sigle or "",
        "origin_nom":         nom or sigle or "Instance",
        "sujet":              msg.sujet or "",
        "contenu":            msg.contenu or "",
    }
    try:
        async with httpx.AsyncClient(timeout=20, verify=False) as cli:
            r = await cli.post(url, data=data,
                               headers={"Authorization": f"Bearer {token}"})
            logger.info("[messagerie] agent fédéré → %s/%s : HTTP %s : %s",
                        target_sigle, recipient_username, r.status_code,
                        (r.text or "")[:160])
    except Exception as e:
        logger.warning("[messagerie] agent fédéré ÉCHEC réseau vers %s : %s", url, e)




# ── v3000h48 — Ingestion inter-nœud (transport messagerie instance ↔ collecteur)
# Endpoint symétrique présent côté instance ET côté collecteur (même plugin).
# Reçoit un message + PJ d'un autre nœud et le crée comme message REÇU local.
# Auth par jeton de nœud (header/Form node_token) validé contre SCRIBE_NODE_TOKEN
# si défini (sinon ouvert, pour démo/dev). Idempotent via source_uuid.
@router.post("/ingest")
async def ingest_message(
    request: Request,
    origin_sigle: str = Form(""),
    origin_nom:   str = Form("Externe"),
    sujet:        str = Form(""),
    contenu:      str = Form(""),
    source_uuid:  str = Form(""),
    recipient_username: str = Form(""),
    node_token:   str = Form(""),
    fichiers:     list[UploadFile] = File([]),
    db:   Session = Depends(get_db),
):
    expected = os.getenv("SCRIBE_NODE_TOKEN")
    if expected and node_token != expected:
        raise HTTPException(401, "Jeton de nœud invalide")

    # Idempotence : si déjà ingéré (même source_uuid), on ne duplique pas.
    if source_uuid:
        dup = db.query(Message).filter(Message.rfc_message_id == source_uuid).first()
        if dup:
            return {"ok": True, "id": dup.id, "dedup": True}

    # Destinataire local : résolu par username si fourni.
    dests = []
    if recipient_username:
        u = db.query(User).filter(User.username == recipient_username).first()
        if u:
            dests = [{"type": "user", "value": u.id, "display": u.display_name or u.username}]
    # Si aucun destinataire résolu (ex. message de la SUPERVISION sans cible nominative)
    # → diffuser à la cellule de crise locale pour que le message soit VISIBLE en boîte.
    # Sinon destinataires=[] et le message n'apparaît dans aucune inbox.
    if not dests:
        try:
            pool = db.query(User).filter(User.active == True).all()
        except Exception:
            pool = []
        _crisis_roles = ("admin", "cellule_crise", "directeur_crise", "dir_crise",
                          "direction", "cadre", "directeur")
        crisis = [u for u in pool if str(getattr(u, "role", "") or "").lower() in _crisis_roles]
        targets = crisis or pool
        dests = [{"type": "user", "value": u.id,
                  "display": (getattr(u, "display_name", None) or u.username)} for u in targets]

    msg = Message(
        canal           = "interne",
        direction       = "in",
        expediteur_id   = None,
        expediteur_nom  = origin_nom or origin_sigle or "Externe",
        expediteur_addr = origin_sigle or "",
        destinataires   = dests,
        destinataires_cc = [],
        destinataires_bcc = [],
        sujet           = sujet,
        contenu         = contenu,
        contenu_format  = "plain",
        thread_id       = "",
        reply_to_id     = None,
        rfc_message_id  = source_uuid or None,
        statut          = "received",
        lu              = False,
        backend_meta    = {"origin": origin_sigle, "ingested": True},
        created_at      = datetime.now(timezone.utc),
    )
    db.add(msg)
    db.flush()

    saved_count = 0
    total_size = 0
    if fichiers:
        target_dir = _ensure_uploads_dir(msg.id)
        for upload in fichiers:
            if saved_count >= MAX_ATTACHMENTS_PER_MSG:
                break
            safe_name = _safe_filename(upload.filename or f"file_{saved_count}")
            dest_path = target_dir / safe_name
            idx = 1
            while dest_path.exists():
                stem = safe_name.rsplit(".", 1)
                dest_path = target_dir / (f"{stem[0]}_{idx}.{stem[1]}" if len(stem) == 2 else f"{safe_name}_{idx}")
                idx += 1
            h = hashlib.sha256()
            size = 0
            with open(dest_path, "wb") as out:
                while True:
                    chunk = await upload.read(65536)
                    if not chunk:
                        break
                    if size + len(chunk) > MAX_ATTACHMENT_SIZE:
                        out.close()
                        try: dest_path.unlink()
                        except OSError: pass
                        raise HTTPException(413, f"PJ trop volumineuse : {upload.filename}")
                    h.update(chunk); out.write(chunk); size += len(chunk); total_size += len(chunk)
            db.add(MessageAttachment(
                message_id=msg.id, kind="local",
                nom=upload.filename or safe_name, taille=size,
                mime=upload.content_type or "application/octet-stream",
                sha256=h.hexdigest(), storage_path=str(dest_path),
            ))
            saved_count += 1

    msg.attachments_count = saved_count
    db.commit()
    db.refresh(msg)
    logger.info("[messagerie] message ingéré de %s (#%s, %s PJ)", origin_sigle or "?", msg.id, saved_count)
    return {"ok": True, "id": msg.id, "attachments": saved_count}



def _safe_filename(name: str) -> str:
    # Garde alphanum + . _ - ()
    import re
    name = name.strip()
    name = re.sub(r"[^\w\.\-\(\)\s]", "_", name)
    return name[:120] or "file"


@router.post("/messages/{msg_id}/reply")
def reply_message(
    msg_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Prépare une réponse : retourne le contexte (destinataire = expéditeur original,
    sujet = "Re: ...", thread_id hérité). Ne crée PAS le message — c'est le composer
    qui le créera après saisie. Mais on prépare un brouillon vide pour l'UI.
    """
    if not user:
        raise HTTPException(401)
    src = db.query(Message).filter(Message.id == msg_id).first()
    if not src or not _can_access(src, user.id):
        raise HTTPException(404, "Message introuvable")

    # Destinataire = expéditeur du message original (si user, sinon vide)
    dest = []
    if src.expediteur_id and src.expediteur_id != user.id:
        exp = db.query(User).filter(User.id == src.expediteur_id).first()
        if exp:
            dest.append({"type":"user","value":exp.id,
                         "display":exp.display_name or exp.username})

    sujet = src.sujet or ""
    if not sujet.lower().startswith("re:"):
        sujet = f"Re: {sujet}"

    return {
        "reply_to_id":  src.id,
        "thread_id":    src.thread_id,
        "destinataires": dest,
        "sujet":        sujet[:500],
        "quote":        _build_quote(src),
    }


@router.post("/messages/{msg_id}/reply-all")
def reply_all_message(
    msg_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Comme reply, mais ajoute aussi tous les destinataires originaux (sauf moi-même)."""
    if not user:
        raise HTTPException(401)
    src = db.query(Message).filter(Message.id == msg_id).first()
    if not src or not _can_access(src, user.id):
        raise HTTPException(404, "Message introuvable")

    dest = []
    seen_ids = set()
    # Expéditeur original
    if src.expediteur_id and src.expediteur_id != user.id:
        exp = db.query(User).filter(User.id == src.expediteur_id).first()
        if exp:
            dest.append({"type":"user","value":exp.id,
                         "display":exp.display_name or exp.username})
            seen_ids.add(exp.id)
    # + tous les autres destinataires originaux (sauf moi)
    for d in (src.destinataires or []):
        if d.get("type") == "user":
            try:
                uid = int(d.get("value"))
            except (TypeError, ValueError):
                continue
            if uid == user.id or uid in seen_ids:
                continue
            u = db.query(User).filter(User.id == uid, User.active == True).first()
            if u:
                dest.append({"type":"user","value":u.id,
                             "display":u.display_name or u.username})
                seen_ids.add(uid)

    sujet = src.sujet or ""
    if not sujet.lower().startswith("re:"):
        sujet = f"Re: {sujet}"

    return {
        "reply_to_id":  src.id,
        "thread_id":    src.thread_id,
        "destinataires": dest,
        "sujet":        sujet[:500],
        "quote":        _build_quote(src),
    }


@router.post("/messages/{msg_id}/forward")
def forward_message(
    msg_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Prépare un transfert : sujet = "Fwd: ...", contenu pré-rempli avec citation,
    pas de destinataires (l'utilisateur les saisit). PJ originales référencées
    (le composer les attachera ou pas selon l'UI).
    """
    if not user:
        raise HTTPException(401)
    src = db.query(Message).filter(Message.id == msg_id).first()
    if not src or not _can_access(src, user.id):
        raise HTTPException(404, "Message introuvable")

    sujet = src.sujet or ""
    if not sujet.lower().startswith("fwd:"):
        sujet = f"Fwd: {sujet}"

    # Liste les PJ pour que le frontend décide quoi inclure
    atts = db.query(MessageAttachment).filter(MessageAttachment.message_id == src.id).all()

    return {
        "thread_id":    _gen_thread_id(),   # nouveau thread pour le transfert
        "destinataires": [],
        "sujet":        sujet[:500],
        "quote":        _build_quote(src),
        "original_attachments": [a.to_dict() for a in atts],
    }


def _build_quote(src: Message) -> str:
    """Construit la citation à insérer dans une réponse / transfert."""
    sender = src.expediteur_nom or "—"
    when = src.sent_at or src.created_at
    when_str = when.strftime("%d/%m/%Y %H:%M") if when else "?"
    body = src.contenu or ""
    quoted = "\n".join("> " + line for line in body.split("\n"))
    return f"\n\nLe {when_str}, {sender} a écrit :\n{quoted}"


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES — Actions sur un message existant
# ─────────────────────────────────────────────────────────────────────────────
@router.patch("/messages/{msg_id}")
def patch_message(
    msg_id: int,
    body:   MessagePatch,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Maj d'attributs d'un message :
        lu, flag_important, folder_id, contenu_redacted
    """
    if not user:
        raise HTTPException(401)
    m = db.query(Message).filter(Message.id == msg_id).first()
    if not m or not _can_access(m, user.id):
        raise HTTPException(404, "Message introuvable")

    if body.lu is not None:
        m.lu = body.lu
        m.lu_at = datetime.now(timezone.utc) if body.lu else None

    if body.flag_important is not None:
        m.flag_important = body.flag_important

    if body.folder_id is not None:
        if body.folder_id == 0:
            m.folder_id = None
        else:
            # Vérifier qu'il appartient à l'user
            f = db.query(Folder).filter(Folder.id == body.folder_id,
                                         Folder.user_id == user.id).first()
            if not f:
                raise HTTPException(404, "Dossier introuvable")
            m.folder_id = f.id

    if body.contenu_redacted is True:
        # Caviardage : seul l'expéditeur peut caviarder son propre message
        if m.expediteur_id != user.id:
            raise HTTPException(403, "Seul l'expéditeur peut caviarder son message")
        m.contenu_redacted = True
        m.contenu = "[CONTENU SUPPRIMÉ PAR L'EXPÉDITEUR]"

    db.commit()
    db.refresh(m)
    return _msg_to_display(m, db, user.id)


@router.delete("/messages/{msg_id}")
def soft_delete_message(
    msg_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Place le message dans la corbeille (soft delete)."""
    if not user:
        raise HTTPException(401)
    m = db.query(Message).filter(Message.id == msg_id).first()
    if not m or not _can_access(m, user.id):
        raise HTTPException(404, "Message introuvable")
    if m.deleted_at:
        return {"ok": True, "already_trashed": True}
    m.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.post("/messages/{msg_id}/restore")
def restore_message(
    msg_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)
    m = db.query(Message).filter(Message.id == msg_id).first()
    if not m or not _can_access(m, user.id):
        raise HTTPException(404, "Message introuvable")
    m.deleted_at = None
    db.commit()
    return {"ok": True}


@router.delete("/messages/{msg_id}/permanent")
def permanent_delete_message(
    msg_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Suppression définitive. Doit être déjà dans la corbeille. Supprime les PJ disque."""
    if not user:
        raise HTTPException(401)
    m = db.query(Message).filter(Message.id == msg_id).first()
    if not m or not _can_access(m, user.id):
        raise HTTPException(404, "Message introuvable")
    if not m.deleted_at:
        raise HTTPException(400, "Doit d'abord être dans la corbeille")
    # Supprimer les PJ disque
    atts = db.query(MessageAttachment).filter(MessageAttachment.message_id == m.id).all()
    for a in atts:
        if a.kind == "local" and a.storage_path:
            try:
                Path(a.storage_path).unlink(missing_ok=True)
            except Exception:
                pass
    # Supprimer le dossier du message si vide
    msg_dir = UPLOADS_BASE / str(m.id)
    if msg_dir.exists():
        try:
            shutil.rmtree(msg_dir, ignore_errors=True)
        except Exception:
            pass
    # CASCADE devrait supprimer les MessageAttachment automatiquement
    db.delete(m)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# ATTACHMENTS
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/attachments/{att_id}")
def download_attachment(
    att_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user:
        raise HTTPException(401)
    a = db.query(MessageAttachment).filter(MessageAttachment.id == att_id).first()
    if not a:
        raise HTTPException(404, "Pièce jointe introuvable")
    m = db.query(Message).filter(Message.id == a.message_id).first()
    if not m or not _can_access(m, user.id):
        raise HTTPException(403)
    if a.kind != "local" or not a.storage_path:
        raise HTTPException(400, "PJ non locale (probablement Bluefiles)")
    p = Path(a.storage_path)
    if not p.exists():
        raise HTTPException(410, "Fichier disparu du disque")
    return FileResponse(path=str(p), filename=a.nom, media_type=a.mime or "application/octet-stream")


@router.delete("/attachments/{att_id}")
def delete_attachment(
    att_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supprime une PJ — seul l'expéditeur peut, et seulement sur un brouillon."""
    if not user:
        raise HTTPException(401)
    a = db.query(MessageAttachment).filter(MessageAttachment.id == att_id).first()
    if not a:
        raise HTTPException(404)
    m = db.query(Message).filter(Message.id == a.message_id).first()
    if not m or m.expediteur_id != user.id:
        raise HTTPException(403)
    if m.statut != "draft":
        raise HTTPException(400, "PJ ne peut être supprimée que sur un brouillon")
    if a.storage_path:
        try: Path(a.storage_path).unlink(missing_ok=True)
        except Exception: pass
    db.delete(a)
    m.attachments_count = max(0, (m.attachments_count or 1) - 1)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# COMPAT LEGACY — pour ne pas casser le frontend transitoirement
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/non-lus")
def non_lus_compat(
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[LEGACY] Count des messages non lus dans l'inbox (canal interne)."""
    if not user:
        return {"count": 0}
    n = db.query(Message).filter(
        Message.canal == "interne",
        Message.deleted_at.is_(None),
        Message.statut != "draft",
        Message.lu == False,
    ).filter(_user_inbox_predicate(user.id)).count()
    return {"count": n}


@router.put("/{msg_id}/lire")
def mark_read_compat(
    msg_id: int,
    db:   Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[LEGACY] Marquer un message comme lu."""
    if not user:
        raise HTTPException(401)
    m = db.query(Message).filter(Message.id == msg_id).first()
    if not m or not _can_access(m, user.id):
        raise HTTPException(404)
    m.lu = True
    m.lu_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
