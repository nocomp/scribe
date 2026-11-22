"""plugins/chat/routes.py"""
import json, os, shutil
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user
from app.models import User
from plugins.chat.models import (
    ChatSalon, ChatMessage, ChatPJ, ChatPresence, ChatConfig,
    ChatSalonMember,  # v3.4 (h34) — membres des salons à visibilité restreinte
)

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def _upload_path(filename: str) -> str:
    """Génère un chemin de stockage avec sous-dossier date et suffixe horodaté."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    subdir = os.path.join(UPLOAD_DIR, now.strftime("%Y-%m-%d"))
    os.makedirs(subdir, exist_ok=True)
    stem, ext = os.path.splitext(filename)
    ts = now.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c for c in stem if c.isalnum() or c in "-_")[:40]
    return os.path.join(subdir, f"{safe}_{ts}{ext}")

# ── Utilitaires ────────────────────────────────────────────────────────────────

def _get_config(db: Session) -> ChatConfig:
    cfg = db.query(ChatConfig).filter(ChatConfig.id == 1).first()
    if not cfg:
        cfg = ChatConfig(id=1)
        db.add(cfg); db.commit(); db.refresh(cfg)
    return cfg

def _auteur_nom(user, sigle: str = "") -> str:
    name = getattr(user, "display_name", None) or getattr(user, "username", "?")
    if sigle:
        return f"{name} [{sigle}]"
    return name

def _sigle_from_config() -> str:
    try:
        config_js = os.environ.get("SCRIBE_CONFIG_JS", "")
        if not config_js:
            for path in ["instances/demo_perm/config.js", "app/static/config.js"]:
                if os.path.exists(path):
                    config_js = path
                    break
        if not config_js or not os.path.exists(config_js):
            return ""
        raw = open(config_js, encoding="utf-8").read()
        start = raw.find("const SCRIBE_CONFIG = ")
        if start < 0:
            return ""
        start += len("const SCRIBE_CONFIG = ")
        end = raw.rfind(";")
        cfg = json.loads(raw[start:end])
        return cfg.get("etablissement", {}).get("sigle", "")
    except Exception:
        return ""


def _fmt_message(m: ChatMessage, db: Session) -> dict:
    pjs = db.query(ChatPJ).filter(ChatPJ.message_id == m.id).all()
    reply = None
    if m.reply_to_id:
        rm = db.query(ChatMessage).filter(ChatMessage.id == m.reply_to_id).first()
        if rm:
            reply = {
                "id": rm.id,
                "auteur_nom": rm.auteur_nom,
                "contenu": (rm.contenu[:80] + "…") if len(rm.contenu) > 80 else rm.contenu
            }
    return {
        "id":           m.id,
        "salon_id":     m.salon_id,
        "auteur_id":    m.auteur_id,
        "auteur_nom":   m.auteur_nom,
        "auteur_sigle": m.auteur_sigle,
        "contenu":      m.contenu if not m.supprime else "_(message supprimé)_",
        "mentions":     json.loads(m.mentions or "[]"),
        "reply_to":     reply,
        "horodatage":   m.horodatage.isoformat() if m.horodatage else None,
        "modifie_at":   m.modifie_at.isoformat() if m.modifie_at else None,
        "supprime":     m.supprime,
        "origine":      m.origine,
        "pj":           [{"id": p.id, "nom": p.nom_fichier, "taille": p.taille_octets} for p in pjs],
    }

def _fmt_salon(s: ChatSalon, db: Optional[Session] = None, current_user_id: Optional[int] = None) -> dict:
    """Sérialise un salon. Pour les DM 1-à-1, calcule le nom et l'icône du
    peer (l'autre participant) afin que le frontend affiche un libellé clair
    type 'Marie Dupont' plutôt que 'dm-3-7' (qui est l'ID technique interne).
    """
    out = {
        "id": s.id, "nom": s.nom, "description": s.description,
        "couleur": s.couleur, "icone": s.icone, "type": s.type,
        "cree_par_id": s.cree_par_id, "cree_at": s.cree_at.isoformat() if s.cree_at else None,
        "archive": s.archive, "ordre": s.ordre, "systeme": s.systeme,
        # v3.4 (h34) — visibilité et flag DM pour le frontend
        "visibility": getattr(s, "visibility", "all") or "all",
        "is_dm": (s.type == "dm"),
    }
    # Pour un DM, calculer les infos du peer
    if s.type == "dm" and db is not None and current_user_id is not None:
        try:
            members = db.query(ChatSalonMember).filter(ChatSalonMember.salon_id == s.id).all()
            peer_ids = [m.user_id for m in members if m.user_id != current_user_id]
            if peer_ids:
                peer = db.query(User).filter(User.id == peer_ids[0]).first()
                if peer:
                    out["peer_user_id"] = peer.id
                    out["peer_display_name"] = peer.display_name or peer.username
                    out["peer_username"] = peer.username
                    # Surcharger le nom affiché : c'est le nom du peer plutôt
                    # que le nom technique du salon "dm-X-Y"
                    out["nom_affiche"] = peer.display_name or peer.username
        except Exception:
            pass
    return out


def _user_can_access_salon(salon: ChatSalon, user_id: int, db: Session) -> bool:
    """v3.4 (h34) — Vérifie qu'un utilisateur peut accéder à un salon.

    Règle :
    - salon avec visibility='all' ou pas de visibility (legacy) → tout le monde y accède
    - salon avec visibility='members_only' (DM ou salons restreints) → seuls les
      membres listés dans chat_salon_members peuvent y accéder
    - admin a accès partout (super-utilisateur)

    Le check admin se fait en amont par le caller s'il le souhaite ; ici on
    se contente du check membership pour rester un helper neutre.
    """
    visibility = getattr(salon, "visibility", "all") or "all"
    if visibility == "all":
        return True
    # members_only : check membership
    is_member = (
        db.query(ChatSalonMember)
        .filter(ChatSalonMember.salon_id == salon.id,
                ChatSalonMember.user_id == user_id)
        .first()
        is not None
    )
    return is_member

def _init_salons(db: Session):
    if db.query(ChatSalon).count() > 0:
        return
    defaults = [
        ChatSalon(nom="général",        description="Canal général", couleur="#003189", icone="📢", type="territorial", systeme=True, ordre=1),
        ChatSalon(nom="coordination-g7", description="Coordination inter-GHT",  couleur="#7c3aed", icone="🌐", type="territorial", systeme=True, ordre=2),
        ChatSalon(nom="transferts",      description="Transferts patients",      couleur="#d97706", icone="🚑", type="territorial", systeme=True, ordre=3),
        ChatSalon(nom="logistique",      description="RH, matériel, ressources", couleur="#16a34a", icone="📦", type="territorial", systeme=True, ordre=4),
        ChatSalon(nom="direction",       description="Directeurs de crise",      couleur="#dc2626", icone="🔴", type="local",        systeme=True, ordre=5),
        ChatSalon(nom="général-local",   description="Communication interne",    couleur="#0891b2", icone="🏥", type="local",        systeme=True, ordre=6),
    ]
    for s in defaults:
        db.add(s)
    db.commit()

def _log_mc(db, user, contenu_court: str):
    """Log léger dans la main courante."""
    try:
        from app.api.sitrep import _create_entry
        _create_entry(db, user, 1, "MIXTE", f"💬 Chat : {contenu_court}", "", "", "")
    except Exception:
        pass

# ── Salons ─────────────────────────────────────────────────────────────────────

@router.get("/salons")
def list_salons(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Liste les salons visibles par l'utilisateur courant.

    v3.4 (h34) — Filtrage selon membership :
    - Salons publics (visibility='all' ou legacy) : visibles par tous
    - Salons restreints (visibility='members_only', incl. DM) :
      visibles uniquement par les membres listés dans chat_salon_members
    - Admin : voit tous les salons (visibilité supervision)
    """
    if not user: raise HTTPException(401)
    _init_salons(db)
    salons = (
        db.query(ChatSalon)
        .filter(ChatSalon.archive == False)
        .order_by(ChatSalon.ordre, ChatSalon.nom)
        .all()
    )
    is_admin = (getattr(user, "role", "") == "admin")
    out = []
    for s in salons:
        if is_admin or _user_can_access_salon(s, user.id, db):
            out.append(_fmt_salon(s, db=db, current_user_id=user.id))
    return out


class SalonIn(BaseModel):
    nom:         str
    description: Optional[str] = None
    couleur:     str = "#003189"
    icone:       str = "💬"
    type:        str = "local"


@router.post("/salons")
def create_salon(body: SalonIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    s = ChatSalon(
        nom=body.nom.strip().lower().replace(" ", "-"),
        description=body.description,
        couleur=body.couleur,
        icone=body.icone,
        type=body.type,
        cree_par_id=user.id,
        ordre=200,
        systeme=False,
    )
    db.add(s); db.commit(); db.refresh(s)
    return _fmt_salon(s)


@router.delete("/salons/{salon_id}")
def delete_salon(salon_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    s = db.query(ChatSalon).filter(ChatSalon.id == salon_id).first()
    if not s: raise HTTPException(404)
    if s.systeme: raise HTTPException(403, "Salon système non supprimable")
    if s.cree_par_id != user.id and getattr(user, "role", "") not in ("admin", "directeur"):
        raise HTTPException(403, "Seul le créateur ou un admin peut supprimer ce salon")
    s.archive = True
    db.commit()
    return {"ok": True}


# ── v3.4 (h34) — Salons privés DM 1-à-1 ────────────────────────────────────────

class DMStart(BaseModel):
    """Démarrer (ou rouvrir) un salon privé entre l'utilisateur courant et
    un autre utilisateur. Si un DM existe déjà entre ces deux utilisateurs,
    le même salon est retourné (pas de duplication)."""
    peer_user_id: int


@router.post("/dm/start")
def dm_start(body: DMStart, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Crée un salon DM 1-à-1 entre l'utilisateur courant et le peer indiqué.

    Comportement idempotent : si un salon DM entre les deux participants
    existe déjà, retourne son ID au lieu d'en créer un nouveau.

    Le salon créé est :
    - type='dm', visibility='members_only'
    - nom = "dm-{minId}-{maxId}" (techniquement, non affiché à l'utilisateur)
    - 2 lignes insérées dans chat_salon_members

    Le frontend ne doit JAMAIS afficher le 'nom' du salon DM. Il doit utiliser
    'peer_display_name' calculé par _fmt_salon(...).
    """
    if not user:
        raise HTTPException(401)
    if body.peer_user_id == user.id:
        raise HTTPException(400, "Impossible de démarrer une conversation avec soi-même")
    peer = db.query(User).filter(User.id == body.peer_user_id, User.active == True).first()
    if not peer:
        raise HTTPException(404, "Utilisateur destinataire introuvable")

    # Cherche un salon DM existant entre les deux utilisateurs.
    # Approche : on prend tous les salons DM dont l'utilisateur courant est
    # membre, puis on vérifie lequel a aussi le peer comme membre.
    existing = (
        db.query(ChatSalon)
        .join(ChatSalonMember, ChatSalonMember.salon_id == ChatSalon.id)
        .filter(ChatSalon.type == "dm",
                ChatSalon.archive == False,
                ChatSalonMember.user_id == user.id)
        .all()
    )
    for s in existing:
        # Salon DM dont le current user est membre. Vérifier que le peer l'est aussi.
        peer_is_member = (
            db.query(ChatSalonMember)
            .filter(ChatSalonMember.salon_id == s.id,
                    ChatSalonMember.user_id == peer.id)
            .first()
            is not None
        )
        if peer_is_member:
            return _fmt_salon(s, db=db, current_user_id=user.id)

    # Aucun salon existant — créer le DM
    min_id = min(user.id, peer.id)
    max_id = max(user.id, peer.id)
    salon = ChatSalon(
        nom=f"dm-{min_id}-{max_id}",
        description=None,
        couleur="#003189",
        icone="💬",
        type="dm",
        visibility="members_only",
        cree_par_id=user.id,
        ordre=10,  # affiché en haut dans la liste mobile
        systeme=False,
    )
    db.add(salon)
    db.flush()  # récupérer l'ID

    # Insérer les 2 lignes member
    db.add(ChatSalonMember(salon_id=salon.id, user_id=user.id))
    db.add(ChatSalonMember(salon_id=salon.id, user_id=peer.id))
    db.commit()
    db.refresh(salon)
    return _fmt_salon(salon, db=db, current_user_id=user.id)


# ── Messages ───────────────────────────────────────────────────────────────────

@router.get("/salons/{salon_id}/messages")
def get_messages(
    salon_id: int,
    limit: int = Query(50, le=200),
    before_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not user: raise HTTPException(401)
    # v3.4 (h34) — Check membership pour les salons à visibilité restreinte
    salon = db.query(ChatSalon).filter(ChatSalon.id == salon_id).first()
    if not salon:
        raise HTTPException(404, "Salon introuvable")
    is_admin = (getattr(user, "role", "") == "admin")
    if not is_admin and not _user_can_access_salon(salon, user.id, db):
        raise HTTPException(403, "Accès refusé à ce salon")
    q = db.query(ChatMessage).filter(ChatMessage.salon_id == salon_id)
    if before_id:
        q = q.filter(ChatMessage.id < before_id)
    msgs = q.order_by(ChatMessage.id.desc()).limit(limit).all()
    msgs.reverse()
    return [_fmt_message(m, db) for m in msgs]


class PJInline(BaseModel):
    nom:     str
    taille:  int = 0
    dataUrl: str = ""  # base64 dataUrl

class MessageIn(BaseModel):
    contenu:     str = ""
    mentions:    List[str] = []
    reply_to_id: Optional[int] = None
    pj_ids:      List[int]  = []   # IDs de PJs uploadées avant envoi
    pj_inline:   List[PJInline] = []  # PJs inline (dataUrl)


@router.post("/salons/{salon_id}/messages")
def post_message(
    salon_id: int,
    body: MessageIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not user: raise HTTPException(401)
    salon = db.query(ChatSalon).filter(ChatSalon.id == salon_id).first()
    if not salon: raise HTTPException(404)
    # v3.4 (h34) — Check membership pour salons restreints (DM 1-à-1)
    is_admin = (getattr(user, "role", "") == "admin")
    if not is_admin and not _user_can_access_salon(salon, user.id, db):
        raise HTTPException(403, "Accès refusé à ce salon")
    # Contenu optionnel si des PJs sont attachées
    if not body.contenu and not body.pj_ids and not body.pj_inline:
        raise HTTPException(400, "Message vide")

    sigle = _sigle_from_config()
    msg = ChatMessage(
        salon_id    = salon_id,
        auteur_id   = user.id,
        auteur_nom  = _auteur_nom(user, sigle),
        auteur_sigle= sigle,
        contenu     = body.contenu,
        mentions    = json.dumps(body.mentions),
        reply_to_id = body.reply_to_id,
        origine     = "local",
    )
    db.add(msg); db.flush()

    # Associer les PJs pré-uploadées (message_id=0) à ce message
    if body.pj_ids:
        for pid in body.pj_ids:
            pj = db.query(ChatPJ).filter(ChatPJ.id == pid, ChatPJ.message_id == 0).first()
            if pj:
                pj.message_id = msg.id

    # Stocker les PJs inline (dataUrl → fichier sur disque)
    if body.pj_inline:
        for pji in body.pj_inline:
            try:
                import base64, os as _os
                data_url = pji.dataUrl
                if "," in data_url:
                    header, b64 = data_url.split(",", 1)
                else:
                    b64 = data_url
                raw = base64.b64decode(b64)
                dest = _upload_path(pji.nom)
                with open(dest, "wb") as fo:
                    fo.write(raw)
                pj_rec = ChatPJ(message_id=msg.id, nom_fichier=pji.nom,
                                taille_octets=len(raw), chemin_stockage=dest)
                db.add(pj_rec)
            except Exception:
                pass

    # Log main courante pour les salons territoriaux
    if salon.type == "territorial":
        extrait = body.contenu[:60] + ("…" if len(body.contenu) > 60 else "")
        _log_mc(db, user, f"#{salon.nom} — {extrait}")

    db.commit(); db.refresh(msg)
    return _fmt_message(msg, db)


@router.delete("/salons/{salon_id}/messages/{msg_id}")
def delete_message(salon_id: int, msg_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    m = db.query(ChatMessage).filter(ChatMessage.id == msg_id, ChatMessage.salon_id == salon_id).first()
    if not m: raise HTTPException(404)
    if m.auteur_id != user.id and getattr(user, "role", "") not in ("admin", "directeur"):
        raise HTTPException(403)
    m.supprime = True; m.modifie_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}

# ── Pièces jointes ─────────────────────────────────────────────────────────────

@router.post("/salons/{salon_id}/pj/upload")
async def upload_pj_temp(
    salon_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Upload une PJ AVANT envoi du message. Retourne un pj_id temporaire (message_id=0)."""
    if not user: raise HTTPException(401)
    cfg = _get_config(db)
    exts = json.loads(cfg.extensions_autorisees)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in exts:
        raise HTTPException(400, f"Extension {ext} non autorisée")
    content = await file.read()
    if len(content) > cfg.taille_max_mo * 1024 * 1024:
        raise HTTPException(400, f"Fichier trop lourd (max {cfg.taille_max_mo} Mo)")
    dest = _upload_path(file.filename)
    with open(dest, "wb") as f_out:
        f_out.write(content)
    pj = ChatPJ(message_id=0, nom_fichier=file.filename,
                taille_octets=len(content), chemin_stockage=dest)
    db.add(pj); db.commit(); db.refresh(pj)
    return {"id": pj.id, "nom": pj.nom_fichier, "taille": pj.taille_octets,
            "ext": ext.lstrip(".").upper()}


@router.post("/salons/{salon_id}/messages/{msg_id}/pj")
async def upload_pj(
    salon_id: int, msg_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not user: raise HTTPException(401)
    cfg = _get_config(db)
    exts = json.loads(cfg.extensions_autorisees)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in exts:
        raise HTTPException(400, f"Extension {ext} non autorisée. Autorisées : {', '.join(exts)}")

    content = await file.read()
    if len(content) > cfg.taille_max_mo * 1024 * 1024:
        raise HTTPException(400, f"Fichier trop lourd (max {cfg.taille_max_mo} Mo)")

    dest = _upload_path(file.filename)
    with open(dest, "wb") as f_out:
        f_out.write(content)

    pj = ChatPJ(message_id=msg_id, nom_fichier=file.filename, taille_octets=len(content), chemin_stockage=dest)
    db.add(pj); db.commit(); db.refresh(pj)
    return {"id": pj.id, "nom": pj.nom_fichier, "taille": pj.taille_octets}


@router.get("/pj/{pj_id}")
def download_pj(
    pj_id: int,
    token: str = None,       # accepté depuis query param pour les <img src>
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    # Authentification : header Authorization OU query param ?token=
    if not user and token:
        from app.api.auth import _decode_token
        from app.models import User
        try:
            payload = _decode_token(token)
            uid = int(payload["sub"])
            user = db.query(User).filter(User.id == uid, User.active == True).first()
        except Exception:
            pass
    if not user: raise HTTPException(401)
    from fastapi.responses import FileResponse
    pj = db.query(ChatPJ).filter(ChatPJ.id == pj_id).first()
    if not pj or not os.path.exists(pj.chemin_stockage): raise HTTPException(404)
    return FileResponse(pj.chemin_stockage, filename=pj.nom_fichier)

# ── Présence ───────────────────────────────────────────────────────────────────

@router.post("/presence/ping")
def ping_presence(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        sigle = _sigle_from_config()
        p = db.query(ChatPresence).filter(ChatPresence.user_id == user.id).first()
        if p:
            p.last_seen = datetime.now(timezone.utc)
            p.display_name = _auteur_nom(user, sigle)
            p.sigle = sigle
        else:
            p = ChatPresence(user_id=user.id, display_name=_auteur_nom(user, sigle), sigle=sigle)
            db.add(p)
        db.commit()
    except Exception as e:
        db.rollback()
        # Créer la table si elle n'existe pas
        try:
            from app.database import engine
            ChatPresence.__table__.create(engine, checkfirst=True)
            db.rollback()
        except Exception:
            pass
    return {"ok": True}


@router.get("/presence")
def get_presence(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    rows = db.query(ChatPresence).filter(ChatPresence.last_seen >= cutoff).all()
    by_sigle = {}
    for r in rows:
        s = r.sigle or "LOCAL"
        if s not in by_sigle: by_sigle[s] = []
        by_sigle[s].append({"user_id": r.user_id, "display_name": r.display_name})
    return by_sigle

# ── Config admin ───────────────────────────────────────────────────────────────

@router.get("/config")
def get_config(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    cfg = _get_config(db)
    return {
        "extensions_autorisees": json.loads(cfg.extensions_autorisees),
        "taille_max_mo": cfg.taille_max_mo,
        "retention_jours": cfg.retention_jours,
    }


class ConfigIn(BaseModel):
    extensions_autorisees: Optional[List[str]] = None
    taille_max_mo:         Optional[int]        = None
    retention_jours:       Optional[int]        = None


@router.patch("/config")
def update_config(body: ConfigIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user or getattr(user, "role", "") not in ("admin", "directeur"):
        raise HTTPException(403)
    cfg = _get_config(db)
    if body.extensions_autorisees is not None:
        cfg.extensions_autorisees = json.dumps(body.extensions_autorisees)
    if body.taille_max_mo is not None:
        cfg.taille_max_mo = body.taille_max_mo
    if body.retention_jours is not None:
        cfg.retention_jours = body.retention_jours
    db.commit()
    return {"ok": True}

# ── Export archive ─────────────────────────────────────────────────────────────

@router.get("/export")
def export_chat(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user: raise HTTPException(401)
    _init_salons(db)
    salons = db.query(ChatSalon).all()
    result = []
    for s in salons:
        msgs = db.query(ChatMessage).filter(
            ChatMessage.salon_id == s.id, ChatMessage.supprime == False
        ).order_by(ChatMessage.id).all()
        result.append({
            "salon": _fmt_salon(s),
            "messages": [_fmt_message(m, db) for m in msgs]
        })
    return result
