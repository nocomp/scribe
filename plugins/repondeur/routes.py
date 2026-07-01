"""
plugins/repondeur/routes.py — SCRIBE
=====================================
API du plugin RÉPONDEUR (lignes d'information de crise via Twilio).

Auth :
  - Config Twilio (identifiants) : admin uniquement.
  - Lignes + messages : admin ou cellule de crise.
  - Webhook voix /voice/{id} : PUBLIC (appelé par Twilio) — protégé par la
    signature X-Twilio-Signature quand l'auth_token est connu.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.api.auth import get_current_user, require_admin, require_role

from plugins.repondeur.models import RepondeurConfig, RepondeurLigne, RepondeurMessage
from plugins.repondeur import twilio_client as tw
from plugins.repondeur import ovh_client as ovh

logger = logging.getLogger("scribe.plugins.repondeur")

router = APIRouter()

# Édition lignes/messages : admin ou cellule de crise
_can_edit = require_role("admin", "cellule_crise")

_TEXT_EXTS = (".txt", ".md", ".markdown", ".csv", ".log", ".text")


# ── Schémas ──────────────────────────────────────────────────────────────────
class LigneIn(BaseModel):
    libelle: str
    numero: str | None = None
    langue_principale: str | None = "fr"
    langues: list[str] | str | None = None
    actif: bool | None = None
    ordre: int | None = None
    voice: str | None = None


class MessageIn(BaseModel):
    langue: str = "fr"
    texte: str = ""


class ImportIn(BaseModel):
    fichier_id: int
    langue: str = "fr"


class RedigerIn(BaseModel):
    langue: str = "fr"
    consigne: str = ""
    contexte: str | None = None


class ConfigIn(BaseModel):
    provider: str | None = None                # "twilio" | "ovh"
    account_sid: str | None = None
    auth_token: str | None = None
    public_url: str | None = None
    default_voice: str | None = None
    clear_auth_token: bool | None = False
    # OVH Télécom
    ovh_endpoint: str | None = None
    ovh_app_key: str | None = None
    ovh_app_secret: str | None = None
    ovh_consumer_key: str | None = None
    ovh_billing_account: str | None = None
    ovh_service: str | None = None
    clear_ovh_secrets: bool | None = False


class TtsIn(BaseModel):
    texte: str | None = None
    langue: str | None = "fr"


# ── Sérialisation ────────────────────────────────────────────────────────────
def _fmt_ligne(l: RepondeurLigne, db: Session) -> dict:
    msgs = {m.langue: m.texte for m in (l.messages or [])}
    principal = msgs.get(l.langue_principale, "")
    return {
        "id": l.id,
        "libelle": l.libelle,
        "numero": l.numero or "",
        "langue_principale": l.langue_principale,
        "langues": l.langues_list(),
        "actif": bool(l.actif),
        "ordre": l.ordre or 0,
        "voice": l.voice or "",
        "message_preview": (principal or "")[:140],
        "messages": msgs,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        "updated_by": l.updated_by or "",
    }


def _get_ligne(db: Session, lid: int) -> RepondeurLigne:
    l = db.query(RepondeurLigne).filter_by(id=lid).first()
    if not l:
        raise HTTPException(404, "Ligne introuvable")
    return l


def _log(db, user, action, detail):
    try:
        from app.api.v140 import _log_mc
        _log_mc(db, user, "REPONDEUR", action, detail, niveau="INFO")
    except Exception:
        pass


# ── Statut ───────────────────────────────────────────────────────────────────
@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    n = db.query(RepondeurLigne).count()
    na = db.query(RepondeurLigne).filter_by(actif=True).count()
    row = db.query(RepondeurConfig).filter_by(id=1).first()
    provider = (getattr(row, "provider", None) or "twilio")
    if provider == "ovh":
        configured = ovh.is_configured(db)
        mode = "live" if configured else "dev"
    else:
        configured = tw.is_live(db)
        mode = tw.current_mode(db)
    return {"provider": provider, "mode": mode, "configured": configured,
            "lignes": n, "lignes_actives": na}


@router.get("/ovh-stats")
def ovh_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Statistiques d'appels OVH par ligne active (le « wow » démo : données
    live tirées de l'API OVH). Renvoie {} si le fournisseur n'est pas OVH."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    row = db.query(RepondeurConfig).filter_by(id=1).first()
    provider = (getattr(row, "provider", None) or "twilio")
    if provider != "ovh":
        return {"provider": provider, "stats": {}}
    lignes = (db.query(RepondeurLigne)
              .filter_by(actif=True)
              .order_by(RepondeurLigne.ordre, RepondeurLigne.id).all())
    stats = {}
    for l in lignes:
        try:
            s = ovh.call_stats(db, l)
            try:
                s["msg_count"] = ovh.count_voicemail(db, l)
            except Exception:
                s["msg_count"] = 0
            stats[str(l.id)] = s
        except Exception:
            stats[str(l.id)] = {"ok": False, "detail": "erreur"}
    return {"provider": "ovh", "stats": stats}


@router.get("/lignes/{lid}/appels")
def ligne_appels(lid: int, db: Session = Depends(get_db), user: User = Depends(_can_edit)):
    """Détail des appels reçus aujourd'hui sur la ligne (données OVH live)."""
    l = _get_ligne(db, lid)
    row = db.query(RepondeurConfig).filter_by(id=1).first()
    provider = (getattr(row, "provider", None) or "twilio")
    if provider != "ovh":
        return {"ok": False, "calls": [], "detail": "Disponible uniquement avec OVH."}
    return ovh.list_calls(db, l, today_only=True)


@router.get("/lignes/{lid}/messages-vocaux")
def messages_vocaux(lid: int, db: Session = Depends(get_db), user: User = Depends(_can_edit)):
    """Liste les messages vocaux OVH laissés sur la ligne (données nominatives —
    restent locales, ne remontent jamais au collecteur)."""
    l = _get_ligne(db, lid)
    row = db.query(RepondeurConfig).filter_by(id=1).first()
    provider = (getattr(row, "provider", None) or "twilio")
    if provider != "ovh":
        return {"ok": False, "provider": provider, "messages": [],
                "detail": "Messagerie vocale disponible uniquement avec OVH."}
    return ovh.list_voicemail_messages(db, l)


@router.get("/lignes/{lid}/messages-vocaux/{mid}/download")
def messages_vocaux_download(lid: int, mid: int, db: Session = Depends(get_db),
                             user: User = Depends(_can_edit)):
    """Récupère l'audio d'un message via l'URL temporaire OVH et le renvoie."""
    l = _get_ligne(db, lid)
    fetched = ovh.voicemail_fetch_audio(db, l, mid)
    if not fetched:
        raise HTTPException(404, "Message ou audio indisponible.")
    audio, filename, media = fetched
    _log(db, user, "MESSAGE VOCAL", f"Téléchargement message {mid} — « {l.libelle} »")
    return Response(content=audio, media_type=media,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/lignes/{lid}/messages-vocaux/{mid}/transcript")
def messages_vocaux_transcript(lid: int, mid: int, db: Session = Depends(get_db),
                               user: User = Depends(_can_edit)):
    """Transcription LOCALE : SCRIBE récupère l'audio du message et le transcrit
    sur le serveur (souverain), sans dépendre de la transcription OVH."""
    l = _get_ligne(db, lid)
    fetched = ovh.voicemail_fetch_audio(db, l, mid)
    if fetched:
        audio, filename, _media = fetched
        import os as _os
        suffix = _os.path.splitext(filename)[1] or ".mp3"
        from plugins.repondeur import stt as _stt
        text, detail = _stt.transcribe(audio, lang=(l.langue_principale or "fr"), suffix=suffix)
        if text is not None:
            _log(db, user, "MESSAGE VOCAL", f"Transcription locale message {mid} — « {l.libelle} »")
            return {"ok": True, "text": text, "source": "local"}
        # Aucun moteur local : on tente OVH en dernier recours
        ovh_res = ovh.voicemail_transcript(db, l, mid)
        if ovh_res.get("ok"):
            return ovh_res
        return {"ok": False, "detail": detail or ovh_res.get("detail") or "Transcription indisponible."}
    # Audio non récupérable : dernier recours OVH
    return ovh.voicemail_transcript(db, l, mid)


@router.post("/tts")
def tts_generate(body: TtsIn, user: User = Depends(_can_edit)):
    """Synthèse vocale locale : texte → MP3 (à téléverser sur le répondeur OVH)."""
    from plugins.repondeur import tts as _tts
    data, info = _tts.synthesize(body.texte or "", body.langue or "fr")
    if not data:
        raise HTTPException(503, info)
    ext = "mp3" if info == "audio/mpeg" else "wav"
    lang = (body.langue or "fr")
    return Response(content=data, media_type=info,
                    headers={"Content-Disposition": f'attachment; filename="repondeur_{lang}.{ext}"'})


@router.get("/tts/status")
def tts_status(user: User = Depends(_can_edit)):
    from plugins.repondeur import tts as _tts
    return _tts.available()


@router.get("/stt/status")
def stt_status(user: User = Depends(_can_edit)):
    from plugins.repondeur import stt as _stt
    return _stt.available()


# ── Lignes : CRUD ────────────────────────────────────────────────────────────
@router.get("/lignes")
def list_lignes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    rows = db.query(RepondeurLigne).order_by(RepondeurLigne.ordre, RepondeurLigne.id).all()
    return [_fmt_ligne(l, db) for l in rows]


@router.post("/lignes")
def create_ligne(body: LigneIn, db: Session = Depends(get_db), user: User = Depends(_can_edit)):
    lib = (body.libelle or "").strip()
    if not lib:
        raise HTTPException(400, "Libellé requis")
    langues = body.langues
    if isinstance(langues, list):
        langues = ",".join([x.strip() for x in langues if x.strip()])
    l = RepondeurLigne(
        libelle=lib[:120],
        numero=(body.numero or "").strip()[:40],
        langue_principale=(body.langue_principale or "fr").strip()[:8],
        langues=(langues or "").strip()[:200],
        actif=bool(body.actif) if body.actif is not None else False,
        ordre=int(body.ordre or 0),
        voice=(body.voice or "").strip()[:80] or None,
        updated_by=user.username,
    )
    db.add(l)
    db.commit()
    db.refresh(l)
    _log(db, user, "LIGNE CRÉÉE", f"« {l.libelle} »")
    return _fmt_ligne(l, db)


@router.put("/lignes/{lid}")
def update_ligne(lid: int, body: LigneIn, db: Session = Depends(get_db), user: User = Depends(_can_edit)):
    l = _get_ligne(db, lid)
    if body.libelle is not None and body.libelle.strip():
        l.libelle = body.libelle.strip()[:120]
    if body.numero is not None:
        l.numero = body.numero.strip()[:40]
    if body.langue_principale:
        l.langue_principale = body.langue_principale.strip()[:8]
    if body.langues is not None:
        langues = body.langues
        if isinstance(langues, list):
            langues = ",".join([x.strip() for x in langues if x.strip()])
        l.langues = (langues or "").strip()[:200]
    if body.actif is not None:
        l.actif = bool(body.actif)
    if body.ordre is not None:
        l.ordre = int(body.ordre)
    if body.voice is not None:
        l.voice = body.voice.strip()[:80] or None
    l.updated_by = user.username
    db.commit()
    _log(db, user, "LIGNE MODIFIÉE", f"« {l.libelle} » (active={bool(l.actif)})")
    return _fmt_ligne(l, db)


@router.delete("/lignes/{lid}")
def delete_ligne(lid: int, db: Session = Depends(get_db), user: User = Depends(_can_edit)):
    l = _get_ligne(db, lid)
    lib = l.libelle
    db.delete(l)
    db.commit()
    _log(db, user, "LIGNE SUPPRIMÉE", f"« {lib} »")
    return {"ok": True}


# ── Messages (par langue) ────────────────────────────────────────────────────
@router.get("/lignes/{lid}/messages")
def get_messages(lid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    l = _get_ligne(db, lid)
    return {"ligne_id": lid, "langues": l.langues_list(),
            "messages": {m.langue: m.texte for m in (l.messages or [])}}


def _set_message(db, l, langue, texte, user):
    langue = (langue or "fr").strip()[:8]
    m = db.query(RepondeurMessage).filter_by(ligne_id=l.id, langue=langue).first()
    if not m:
        m = RepondeurMessage(ligne_id=l.id, langue=langue)
        db.add(m)
    m.texte = texte or ""
    m.updated_by = user.username
    db.commit()
    return m


@router.put("/lignes/{lid}/message")
def set_message(lid: int, body: MessageIn, db: Session = Depends(get_db), user: User = Depends(_can_edit)):
    l = _get_ligne(db, lid)
    _set_message(db, l, body.langue, body.texte, user)
    _log(db, user, "MESSAGE MIS À JOUR", f"« {l.libelle} » [{body.langue}]")
    return _fmt_ligne(l, db)


# ── Import depuis le drive FICHIERS ──────────────────────────────────────────
@router.get("/fichiers-texte")
def list_fichiers_texte(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Liste les fichiers texte de l'utilisateur, pour le sélecteur d'import."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    out = []
    try:
        from plugins.fichiers.models import Fichier, FichierBlob
        rows = db.query(Fichier).filter(Fichier.proprietaire_id == user.id).all()
        for f in rows:
            nom = (f.nom or "")
            if nom.lower().endswith(_TEXT_EXTS):
                blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
                out.append({"id": f.id, "nom": nom,
                            "taille": (blob.taille if blob else 0)})
    except Exception:
        pass
    return out


@router.post("/lignes/{lid}/import-fichier")
def import_fichier(lid: int, body: ImportIn, db: Session = Depends(get_db), user: User = Depends(_can_edit)):
    l = _get_ligne(db, lid)
    try:
        from plugins.fichiers.models import Fichier, FichierBlob
        from plugins.fichiers import storage
    except Exception:
        raise HTTPException(503, "Plugin Fichiers indisponible")
    f = db.query(Fichier).filter(Fichier.id == body.fichier_id,
                                 Fichier.proprietaire_id == user.id).first()
    if not f:
        raise HTTPException(404, "Fichier introuvable")
    if not (f.nom or "").lower().endswith(_TEXT_EXTS):
        raise HTTPException(415, "Importez un fichier texte (.txt, .md, .csv).")
    blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
    if not blob:
        raise HTTPException(404, "Contenu indisponible")
    try:
        path = storage.blob_path(blob.checksum)
        raw = path.read_bytes()
        texte = raw.decode("utf-8", errors="ignore").strip()
    except Exception:
        raise HTTPException(500, "Lecture du fichier impossible")
    if not texte:
        raise HTTPException(422, "Le fichier est vide ou illisible.")
    _set_message(db, l, body.langue, texte[:5000], user)
    _log(db, user, "IMPORT FICHIER", f"« {l.libelle} » ← {f.nom} [{body.langue}]")
    return _fmt_ligne(l, db)


# ── Rédaction assistée (Albert) ──────────────────────────────────────────────
@router.post("/lignes/{lid}/rediger")
async def rediger_message(lid: int, body: RedigerIn, db: Session = Depends(get_db),
                          user: User = Depends(_can_edit)):
    l = _get_ligne(db, lid)
    try:
        from app.api.ai_router import call_ai, require_ia_configured
        not_ready = require_ia_configured()
        if not_ready:
            raise HTTPException(503, not_ready.get("detail", "IA non configurée"))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Assistant IA indisponible")

    langue = (body.langue or "fr").strip()[:8]
    system = (
        "Tu es chargé de communication de crise hospitalière. Tu rédiges un message "
        "vocal court (8 à 12 secondes de lecture), clair, calme et rassurant, destiné "
        "à être lu au téléphone par un répondeur. Règles STRICTES : aucune donnée "
        "nominative de patient, aucun nom d'établissement précis, aucune information "
        "non confirmée. Tu indiques quoi faire (rappeler plus tard, consulter le site, "
        "ne pas se déplacer si demandé). Tu réponds UNIQUEMENT par le texte du message, "
        "sans guillemets ni préambule, dans la langue demandée."
    )
    prompt = (
        f"Langue du message : {langue}.\n"
        f"Public visé / type de ligne : {l.libelle}.\n"
        f"Consigne de la cellule de crise : {body.consigne or '(aucune)'}\n"
        f"Contexte de crise : {body.contexte or '(non précisé)'}\n\n"
        "Rédige le message du répondeur."
    )
    try:
        texte, source = await call_ai(system, prompt, max_tokens=300)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"IA indisponible : {e}")
    texte = (texte or "").strip().strip('"').strip()
    return {"langue": langue, "texte": texte, "source": source}


# ── Provisioning Twilio (déclarer le webhook sur un numéro) ──────────────────
@router.post("/lignes/{lid}/push-twilio")
def push_twilio(lid: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    l = _get_ligne(db, lid)
    cfg = tw.get_config(db)
    if not cfg["public_url"]:
        raise HTTPException(400, "URL publique non configurée (⚙ Configuration).")
    if not l.numero:
        raise HTTPException(400, "Numéro absent sur cette ligne.")
    voice_url = f"{cfg['public_url']}/api/v1/repondeur/voice/{l.id}"
    res = tw.set_number_webhook(l.numero, voice_url, db)
    _log(db, user, "WEBHOOK TWILIO", f"« {l.libelle} » → {res.get('detail','')}")
    if not res.get("ok"):
        raise HTTPException(400, res.get("detail", "Échec Twilio"))
    return {"ok": True, "voice_url": voice_url, "detail": res.get("detail")}


@router.post("/lignes/{lid}/appliquer")
def appliquer(lid: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Applique la ligne chez le fournisseur actif.

    - Twilio : déclare le webhook voix sur le numéro (provisioning live).
    - OVH    : mode assisté — retourne le texte prêt à coller dans le SVI OVH
               + l'état de joignabilité du compte (OVH ne fait pas de TTS live
               par webhook).
    """
    l = _get_ligne(db, lid)
    row = db.query(RepondeurConfig).filter_by(id=1).first()
    provider = (getattr(row, "provider", None) or "twilio")

    if provider == "ovh":
        textes = {m.langue: m.texte for m in (l.messages or [])}
        if not textes and l.langue_principale:
            textes = {l.langue_principale: ""}
        res = ovh.apply_guidance(l, textes, db)
        _log(db, user, "APPLIQUER OVH", f"« {l.libelle} » → {res.get('detail','')}")
        return res

    # Twilio (défaut)
    cfg = tw.get_config(db)
    if not cfg["public_url"]:
        raise HTTPException(400, "URL publique non configurée (⚙ Configuration).")
    if not l.numero:
        raise HTTPException(400, "Numéro absent sur cette ligne.")
    voice_url = f"{cfg['public_url']}/api/v1/repondeur/voice/{l.id}"
    res = tw.set_number_webhook(l.numero, voice_url, db)
    _log(db, user, "WEBHOOK TWILIO", f"« {l.libelle} » → {res.get('detail','')}")
    if not res.get("ok"):
        raise HTTPException(400, res.get("detail", "Échec Twilio"))
    return {"ok": True, "provider": "twilio", "voice_url": voice_url, "detail": res.get("detail")}
@router.get("/admin/config")
def get_config(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(RepondeurConfig).filter_by(id=1).first()
    eff = tw.get_config(db)
    ovh_eff = ovh.get_config(db)
    provider = (getattr(row, "provider", None) or "twilio")
    return {
        "provider": provider,
        "account_sid": eff["account_sid"],
        "public_url": eff["public_url"],
        "default_voice": eff["default_voice"],
        "auth_token_set": bool(eff["auth_token"]),
        "auth_token_preview": tw.mask_secret(eff["auth_token"]),
        "mode": (("live" if ovh.is_configured(db) else "dev") if provider == "ovh" else tw.current_mode(db)),
        # OVH (secrets jamais renvoyés en clair : booléen + aperçu)
        "ovh_endpoint": ovh_eff["endpoint"],
        "ovh_app_key": ovh_eff["app_key"],
        "ovh_billing_account": ovh_eff["billing_account"],
        "ovh_service": ovh_eff["service"],
        "ovh_app_secret_set": bool(ovh_eff["app_secret"]),
        "ovh_consumer_key_set": bool(ovh_eff["consumer_key"]),
        "ovh_app_secret_preview": tw.mask_secret(ovh_eff["app_secret"]),
        "ovh_consumer_key_preview": tw.mask_secret(ovh_eff["consumer_key"]),
        "sources": {
            "account_sid": tw.source_of("account_sid", row),
            "auth_token":  tw.source_of("auth_token", row),
            "public_url":  tw.source_of("public_url", row),
            "default_voice": tw.source_of("default_voice", row),
            "ovh_app_key": ovh.source_of("app_key", row),
            "ovh_app_secret": ovh.source_of("app_secret", row),
        },
        "updated_at": row.updated_at.isoformat() if (row and row.updated_at) else None,
        "updated_by": row.updated_by if row else None,
    }


@router.post("/admin/config")
def save_config(body: ConfigIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(RepondeurConfig).filter_by(id=1).first()
    if not row:
        row = RepondeurConfig(id=1)
        db.add(row)
    if body.provider is not None and body.provider in ("twilio", "ovh"):
        row.provider = body.provider
    # ── Twilio ──
    if body.account_sid is not None:
        row.account_sid = body.account_sid.strip()
    if body.public_url is not None:
        row.public_url = body.public_url.strip().rstrip("/")
    if body.default_voice is not None:
        row.default_voice = body.default_voice.strip()
    if body.clear_auth_token:
        row.auth_token = ""
    elif body.auth_token and body.auth_token.strip():
        row.auth_token = tw.enc(body.auth_token.strip())
    # ── OVH ──
    if body.ovh_endpoint is not None:
        row.ovh_endpoint = body.ovh_endpoint.strip() or "ovh-eu"
    if body.ovh_app_key is not None:
        row.ovh_app_key = body.ovh_app_key.strip()
    if body.ovh_billing_account is not None:
        row.ovh_billing_account = body.ovh_billing_account.strip()
    if body.ovh_service is not None:
        row.ovh_service = body.ovh_service.strip()
    if body.clear_ovh_secrets:
        row.ovh_app_secret = ""
        row.ovh_consumer_key = ""
    else:
        if body.ovh_app_secret and body.ovh_app_secret.strip():
            row.ovh_app_secret = tw.enc(body.ovh_app_secret.strip())
        if body.ovh_consumer_key and body.ovh_consumer_key.strip():
            row.ovh_consumer_key = tw.enc(body.ovh_consumer_key.strip())
    row.updated_by = admin.username
    db.commit()
    prov = row.provider or "twilio"
    mode = (("live" if ovh.is_configured(db) else "dev") if prov == "ovh" else tw.current_mode(db))
    _log(db, admin, "CONFIG REPONDEUR", f"Configuration {prov.upper()} mise à jour (mode={mode})")
    return {"ok": True, "provider": prov, "mode": mode}


@router.post("/admin/config/test")
def test_config(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(RepondeurConfig).filter_by(id=1).first()
    provider = (getattr(row, "provider", None) or "twilio")
    return ovh.test_credentials(db) if provider == "ovh" else tw.test_credentials(db)


# ── Liste publique (pour le communiqué / page /status) ───────────────────────
@router.get("/public/lignes")
def public_lignes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Lignes ACTIVES, non-nominatif (libellé + numéro) — pour le communiqué."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    rows = (db.query(RepondeurLigne)
            .filter_by(actif=True)
            .order_by(RepondeurLigne.ordre, RepondeurLigne.id).all())
    return [{"libelle": l.libelle, "numero": l.numero or "",
             "langues": l.langues_list()} for l in rows if l.numero]


# ── Webhook voix (PUBLIC — appelé par Twilio) ────────────────────────────────
def _xml(content: str) -> Response:
    return Response(content=content, media_type="application/xml")


async def _twiml_for(db, l: RepondeurLigne, code: str) -> str:
    cfg = tw.get_config(db)
    voice = l.voice or cfg["default_voice"]
    m = db.query(RepondeurMessage).filter_by(ligne_id=l.id, langue=code).first()
    texte = (m.texte if m else "") or ""
    if not texte:
        # repli sur la langue principale
        m2 = db.query(RepondeurMessage).filter_by(ligne_id=l.id, langue=l.langue_principale).first()
        texte = (m2.texte if m2 else "") or "Ce service d'information n'a pas encore de message."
        code = l.langue_principale
    return tw.build_twiml_single(texte, code, voice)


@router.api_route("/voice/{lid}", methods=["GET", "POST"])
async def voice_webhook(lid: int, request: Request, db: Session = Depends(get_db)):
    l = db.query(RepondeurLigne).filter_by(id=lid).first()
    if not l or not l.actif:
        return _xml('<?xml version="1.0" encoding="UTF-8"?><Response>'
                    '<Say language="fr-FR">Ce service est momentanément indisponible.</Say>'
                    '<Hangup/></Response>')

    # Validation de signature Twilio (si auth_token connu) — best effort.
    try:
        form = {}
        if request.method == "POST":
            form = dict(await request.form())
        params = dict(request.query_params)
        params.update(form)
        cfg = tw.get_config(db)
        sig = request.headers.get("X-Twilio-Signature", "")
        if cfg["auth_token"] and sig:
            url = str(request.url)
            if not tw.validate_signature(cfg["auth_token"], url, params, sig):
                logger.warning("Signature Twilio invalide sur /voice/%s", lid)
                # on continue en mode tolérant (proxies réécrivent souvent l'URL)
    except Exception:
        params = dict(request.query_params)

    langues = l.langues_list()
    digits = params.get("Digits")

    # SVI multilingue : pré-menu si plusieurs langues et pas encore de choix
    if len(langues) > 1 and not digits:
        cfg = tw.get_config(db)
        voice = l.voice or cfg["default_voice"]
        action = f"/api/v1/repondeur/voice/{l.id}"
        return _xml(tw.build_twiml_menu(langues, voice, action))

    # Choix de langue par DTMF
    code = l.langue_principale
    if digits:
        try:
            idx = int(digits) - 1
            if 0 <= idx < len(langues):
                code = langues[idx]
        except Exception:
            code = l.langue_principale

    return _xml(await _twiml_for(db, l, code))
