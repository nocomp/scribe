"""
plugins/fichiers/routes.py — SCRIBE
====================================
API REST du plugin `fichiers` (drive interne SCRIBE).

Périmètre v1 livré :
  - Drive perso : arborescence de dossiers, upload (streaming chunké),
    download, renommer, corbeille (suppression douce) / restauration / purge,
    recherche, favoris.
  - Partage ÉPHÉMÈRE à jeton : le fichier est délivré UNE seule fois puis
    automatiquement effacé (blob purgé s'il devient orphelin).

Sécurité :
  - Auth obligatoire (get_current_user) ; chaque utilisateur ne voit que ses
    fichiers (proprietaire_id).
  - Aucun binaire en DB ; blobs content-addressed sous SCRIBE_DATA_DIR.
  - Audit immuable (qui/quand/quoi), jamais le contenu.
  - Quota par fichier + types MIME bloqués (exécutables) vérifiés à l'écriture.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.database import get_db
from app.api.auth import get_current_user, _hash, _verify, require_admin
from plugins.fichiers import storage
from plugins.fichiers.models import (
    Dossier, Fichier, FichierBlob, JournalFichier, Partage, PartageRangement,
)

router = APIRouter()

# ── Garde-fous (par défaut ; rendus configurables en v2 via /admin/config) ────
MAX_FILE_BYTES = 100 * 1024 * 1024          # 100 Mo / fichier
MIME_BLOQUES = {
    "application/x-msdownload", "application/x-msdos-program",
    "application/x-sh", "application/x-executable", "application/x-dosexec",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, user, action: str, fichier_id: Optional[int], details: str = ""):
    try:
        db.add(JournalFichier(
            action=action, fichier_id=fichier_id,
            acteur=getattr(user, "display_name", None) or getattr(user, "username", "?"),
            acteur_role=getattr(user, "role", ""),
            horodatage=_now(), details=details[:480],
        ))
        db.commit()
    except Exception:
        db.rollback()


def _fmt_fichier(f: Fichier, blob: Optional[FichierBlob]) -> dict:
    try:
        _dispo = bool(blob and storage.blob_path(blob.checksum).exists())
    except Exception:
        _dispo = bool(blob)
    return {
        "id": f.id,
        "nom": f.nom,
        "dossier_id": f.dossier_id,
        "taille": blob.taille if blob else 0,
        "mime": blob.mime if blob else "application/octet-stream",
        "disponible": _dispo,
        "tags": f.tags or "",
        "favori": bool(f.favori),
        "ephemere": bool(getattr(f, "ephemere", False)),
        "download_restreint": bool(getattr(f, "download_restreint", True)),
        "contient_donnees_patient": bool(f.contient_donnees_patient),
        "supprime": bool(f.supprime),
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


# ── Arborescence / listing ───────────────────────────────────────────────────
@router.get("/tree")
def get_tree(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    dossiers = (db.query(Dossier)
                  .filter(Dossier.proprietaire_id == user.id, Dossier.type == "perso")
                  .order_by(Dossier.nom).all())
    return [{"id": d.id, "nom": d.nom, "parent_id": d.parent_id} for d in dossiers]


@router.get("/list")
def list_fichiers(dossier_id: Optional[int] = None,
                  db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    q = (db.query(Fichier)
           .filter(Fichier.proprietaire_id == user.id, Fichier.supprime == False))  # noqa: E712
    if dossier_id:
        q = q.filter(Fichier.dossier_id == dossier_id)
    else:
        q = q.filter(Fichier.dossier_id.is_(None))
    out = []
    for f in q.order_by(Fichier.nom).all():
        blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
        out.append(_fmt_fichier(f, blob))
    return out


@router.get("/corbeille")
def list_corbeille(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    out = []
    for f in (db.query(Fichier)
                .filter(Fichier.proprietaire_id == user.id, Fichier.supprime == True)  # noqa: E712
                .order_by(Fichier.supprime_at.desc()).all()):
        blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
        out.append(_fmt_fichier(f, blob))
    return out


@router.get("/favoris")
def list_favoris(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    out = []
    for f in (db.query(Fichier)
                .filter(Fichier.proprietaire_id == user.id,
                        Fichier.favori == True, Fichier.supprime == False)  # noqa: E712
                .order_by(Fichier.nom).all()):
        blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
        out.append(_fmt_fichier(f, blob))
    return out


@router.get("/search")
def search_fichiers(q: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    terme = (q or "").strip().lower()
    res = []
    if not terme:
        return res
    for f in (db.query(Fichier)
                .filter(Fichier.proprietaire_id == user.id, Fichier.supprime == False)  # noqa: E712
                .all()):
        if terme in (f.nom or "").lower() or terme in (f.tags or "").lower():
            blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
            res.append(_fmt_fichier(f, blob))
    return res


# ── Dossiers ─────────────────────────────────────────────────────────────────
@router.post("/dossier")
async def create_dossier(nom: str = Form(...), parent_id: Optional[int] = Form(None),
                         db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    nom = (nom or "").strip()[:255]
    if not nom:
        raise HTTPException(400, "Nom de dossier requis")
    d = Dossier(nom=nom, parent_id=parent_id, proprietaire_id=user.id, type="perso")
    db.add(d); db.commit(); db.refresh(d)
    return {"id": d.id, "nom": d.nom, "parent_id": d.parent_id}


@router.delete("/dossier/{did}")
def delete_dossier(did: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    d = db.query(Dossier).filter(Dossier.id == did, Dossier.proprietaire_id == user.id).first()
    if not d:
        raise HTTPException(404, "Dossier introuvable")
    # Mettre les fichiers du dossier à la racine (corbeille douce, pas de perte)
    for f in db.query(Fichier).filter(Fichier.dossier_id == did,
                                       Fichier.proprietaire_id == user.id).all():
        f.dossier_id = None
    # Remonter les sous-dossiers au parent du dossier supprimé (pas d'orphelins)
    for sub in db.query(Dossier).filter(Dossier.parent_id == did,
                                        Dossier.proprietaire_id == user.id).all():
        sub.parent_id = d.parent_id
    db.delete(d); db.commit()
    return {"ok": True}


@router.put("/dossier/{did}")
def update_dossier(did: int,
                   nom: Optional[str] = Form(None),
                   parent_id: Optional[str] = Form(None),
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Renomme (nom) et/ou déplace (parent_id) un dossier. parent_id vide / "null"
    / "0" => racine. Garde anti-cycle : on refuse de déplacer un dossier dans
    lui-même ou dans l'un de ses descendants."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    d = db.query(Dossier).filter(Dossier.id == did, Dossier.proprietaire_id == user.id).first()
    if not d:
        raise HTTPException(404, "Dossier introuvable")
    if nom is not None:
        n = (nom or "").strip()[:255]
        if not n:
            raise HTTPException(400, "Nom de dossier requis")
        d.nom = n
    if parent_id is not None:
        pv = (parent_id or "").strip().lower()
        if pv in ("", "null", "0", "none", "racine"):
            d.parent_id = None
        else:
            try:
                new_parent = int(pv)
            except ValueError:
                raise HTTPException(400, "Parent invalide")
            if new_parent == did:
                raise HTTPException(400, "Un dossier ne peut être son propre parent")
            target = db.query(Dossier).filter(Dossier.id == new_parent,
                                              Dossier.proprietaire_id == user.id).first()
            if not target:
                raise HTTPException(404, "Dossier cible introuvable")
            # Anti-cycle : remonter la chaîne des parents de la cible ; on ne doit
            # jamais retomber sur le dossier déplacé.
            cur, hops = target, 0
            while cur is not None and hops < 1000:
                if cur.id == did:
                    raise HTTPException(400, "Déplacement invalide (cycle)")
                cur = (db.query(Dossier).filter(Dossier.id == cur.parent_id).first()
                       if cur.parent_id else None)
                hops += 1
            d.parent_id = new_parent
    db.commit(); db.refresh(d)
    return {"id": d.id, "nom": d.nom, "parent_id": d.parent_id}


# ── Upload (streaming) ───────────────────────────────────────────────────────
@router.post("/upload")
async def upload_fichier(file: UploadFile = File(...),
                         dossier_id: Optional[int] = Form(None),
                         ephemere: Optional[str] = Form(None),
                         download_restreint: Optional[str] = Form(None),
                         contient_donnees_patient: Optional[str] = Form(None),
                         db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    mime = (file.content_type or "application/octet-stream").lower()
    if mime in MIME_BLOQUES:
        raise HTTPException(415, "Type de fichier non autorisé")
    # Politique d'upload : config admin du plugin (catégories MIME + taille),
    # sinon politique centrale 'uploads', sinon défaut.
    try:
        from app.plugin_settings import enforce as _enf
        _eff_max = _enf("fichiers", file.filename, MAX_FILE_BYTES)
    except HTTPException:
        raise
    except Exception:
        _eff_max = MAX_FILE_BYTES
    try:
        checksum, taille, rel = storage.store_stream(file.file, max_bytes=_eff_max)
    except ValueError:
        raise HTTPException(413, "Fichier trop volumineux")
    except Exception:
        raise HTTPException(500, "Échec de l'enregistrement")

    blob = db.query(FichierBlob).filter(FichierBlob.checksum == checksum).first()
    if not blob:
        blob = FichierBlob(checksum=checksum, taille=taille, mime=mime, chemin_stockage=rel)
        db.add(blob); db.commit(); db.refresh(blob)

    is_patient = str(contient_donnees_patient or "").lower() in ("1", "true", "on", "oui")
    is_eph = str(ephemere or "").lower() in ("1", "true", "on", "oui")
    # Défaut sécurisé : restreint coché sauf si explicitement désactivé.
    is_restreint = str(download_restreint if download_restreint is not None else "1").lower() \
        in ("1", "true", "on", "oui")
    f = Fichier(nom=(file.filename or "fichier")[:255], dossier_id=dossier_id,
                proprietaire_id=user.id, blob_id=blob.id,
                ephemere=is_eph, download_restreint=is_restreint,
                contient_donnees_patient=is_patient)
    db.add(f); db.commit(); db.refresh(f)
    _audit(db, user, "upload", f.id, f"{f.nom} ({taille} o)" + (" [éphémère]" if is_eph else "")
           + (" [restreint]" if is_restreint else ""))
    return _fmt_fichier(f, blob)


# ── Download ─────────────────────────────────────────────────────────────────
def _get_owned(db: Session, user, fid: int) -> Fichier:
    f = db.query(Fichier).filter(Fichier.id == fid,
                                 Fichier.proprietaire_id == user.id).first()
    if not f:
        raise HTTPException(404, "Fichier introuvable")
    return f


@router.get("/download/{fid}")
def download_fichier(fid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fid)
    blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
    if not blob or not storage.blob_path(blob.checksum).exists():
        raise HTTPException(404, "Contenu indisponible")
    _audit(db, user, "download", f.id, f.nom)
    headers = {"Content-Disposition": f'attachment; filename="{f.nom}"'}
    return StreamingResponse(storage.iter_blob(blob.checksum),
                             media_type=blob.mime, headers=headers)


# ── Renommer / favori / corbeille ────────────────────────────────────────────
@router.put("/rename/{fid}")
async def rename_fichier(fid: int, nom: str = Form(...),
                         db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fid)
    nv = (nom or "").strip()[:255]
    if not nv:
        raise HTTPException(400, "Nom requis")
    f.nom = nv; db.commit()
    return _fmt_fichier(f, db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first())


@router.post("/favori/{fid}")
def toggle_favori(fid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fid)
    f.favori = not bool(f.favori); db.commit()
    return {"id": f.id, "favori": bool(f.favori)}


@router.delete("/{fid}")
def delete_fichier(fid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Suppression DOUCE → corbeille."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fid)
    f.supprime = True; f.supprime_at = _now(); db.commit()
    _audit(db, user, "suppression", f.id, f.nom)
    return {"ok": True}


@router.post("/restore/{fid}")
def restore_fichier(fid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fid)
    f.supprime = False; f.supprime_at = None; db.commit()
    return {"ok": True}


@router.delete("/purge/{fid}")
def purge_fichier(fid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Suppression DÉFINITIVE du nœud + purge du blob s'il devient orphelin."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fid)
    blob_id = f.blob_id
    db.query(Partage).filter(Partage.fichier_id == f.id).delete()
    db.delete(f); db.commit()
    _purge_blob_if_orphan(db, blob_id)
    _audit(db, user, "purge", None, f"fichier #{fid}")
    return {"ok": True}


def _purge_blob_if_orphan(db: Session, blob_id: int) -> None:
    """Supprime le blob (disque + DB) si plus aucun Fichier ne le référence."""
    still = db.query(Fichier).filter(Fichier.blob_id == blob_id).count()
    if still == 0:
        blob = db.query(FichierBlob).filter(FichierBlob.id == blob_id).first()
        if blob:
            storage.delete_blob(blob.checksum)
            db.delete(blob); db.commit()


# ── Partage ÉPHÉMÈRE (auto-destruction après téléchargement) ──────────────────
@router.post("/partage-ephemere")
async def creer_partage_ephemere(fichier_id: int = Form(...),
                                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Crée un lien à jeton à USAGE UNIQUE. Après le premier téléchargement,
    le lien est consommé ; si le fichier sous-jacent est marqué ÉPHÉMÈRE, il est
    aussi effacé (blob purgé si orphelin). Un fichier permanent reste en place.
    Le garde-fou « données patient » ne bloque que la fédération/supervision."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fichier_id)
    if f.supprime:
        raise HTTPException(400, "Fichier en corbeille")
    jeton = secrets.token_urlsafe(24)
    p = Partage(fichier_id=f.id, jeton=jeton, cible_type="lien",
                droit="lecture", ephemere=True, created_by=user.id)
    db.add(p); db.commit(); db.refresh(p)
    _audit(db, user, "ephemere", f.id, f"lien éphémère {jeton[:8]}…")
    return {"id": p.id, "jeton": jeton, "url": f"/api/v1/fichiers/e/{jeton}",
            "ephemere": True, "nom": f.nom}


@router.post("/partage-permanent")
async def creer_partage_permanent(fichier_id: int = Form(...),
                                  db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Crée un lien à jeton PERMANENT (multi-téléchargement, ne supprime rien).
    Réutilise un lien permanent existant pour le même fichier si présent."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fichier_id)
    if f.supprime:
        raise HTTPException(400, "Fichier en corbeille")
    if getattr(f, "ephemere", False):
        raise HTTPException(400, "Un fichier éphémère ne peut avoir de lien permanent")
    existing = (db.query(Partage)
                  .filter(Partage.fichier_id == f.id, Partage.ephemere == False,  # noqa: E712
                          Partage.created_by == user.id).first())
    if existing:
        return {"id": existing.id, "jeton": existing.jeton,
                "url": f"/api/v1/fichiers/p/{existing.jeton}", "ephemere": False, "nom": f.nom}
    jeton = secrets.token_urlsafe(24)
    p = Partage(fichier_id=f.id, jeton=jeton, cible_type="lien",
                droit="lecture", ephemere=False, created_by=user.id)
    db.add(p); db.commit(); db.refresh(p)
    _audit(db, user, "partage", f.id, f"lien permanent {jeton[:8]}…")
    return {"id": p.id, "jeton": jeton, "url": f"/api/v1/fichiers/p/{jeton}",
            "ephemere": False, "nom": f.nom}


@router.get("/p/{jeton}")
def telecharger_permanent(jeton: str, db: Session = Depends(get_db)):
    """Téléchargement via lien permanent (jeton). Aucune suppression."""
    p = db.query(Partage).filter(Partage.jeton == jeton, Partage.ephemere == False).first()  # noqa: E712
    if not p:
        raise HTTPException(404, "Lien inconnu")
    if p.restreint:
        # Un lien restreint ne se télécharge que via /d/ (auth + ACL).
        raise HTTPException(403, "Lien restreint : téléchargement réservé aux destinataires")
    if p.expire_at and p.expire_at < _now():
        raise HTTPException(410, "Lien expiré")
    f = db.query(Fichier).filter(Fichier.id == p.fichier_id).first()
    if not f or f.supprime:
        raise HTTPException(410, "Fichier indisponible")
    blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
    if not blob or not storage.blob_path(blob.checksum).exists():
        raise HTTPException(410, "Contenu indisponible")
    headers = {"Content-Disposition": f'attachment; filename="{f.nom}"'}
    return StreamingResponse(storage.iter_blob(blob.checksum), media_type=blob.mime, headers=headers)


@router.get("/d/{jeton}")
def telecharger_restreint(jeton: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Téléchargement SÉCURISÉ : la session authentifiée fait foi.

    - Pas de session valide  → 401 (un lien recopié en navigation privée échoue).
    - Connecté mais hors liste des destinataires → 403 (un lien transféré à un
      tiers est inutilisable).
    - Destinataire prévu      → 200, le fichier est délivré.

    Pour un partage éphémère, le lien est consommé après le premier
    téléchargement (et le fichier effacé s'il est lui-même éphémère)."""
    if not user:
        raise HTTPException(401, "Authentification requise pour ce téléchargement")
    p = db.query(Partage).filter(Partage.jeton == jeton).first()
    if not p:
        raise HTTPException(404, "Lien inconnu")
    if p.restreint:
        allowed = {int(x) for x in (p.destinataires_uids or "").split(",") if x.strip().isdigit()}
        owner_id = None
        f0 = db.query(Fichier).filter(Fichier.id == p.fichier_id).first()
        if f0:
            owner_id = f0.proprietaire_id
        if user.id not in allowed and user.id != owner_id:
            raise HTTPException(403, "Téléchargement réservé aux destinataires de ce partage")
    if p.expire_at and p.expire_at < _now():
        raise HTTPException(410, "Lien expiré")
    if p.ephemere and p.telecharge:
        raise HTTPException(410, "Lien déjà utilisé")
    f = db.query(Fichier).filter(Fichier.id == p.fichier_id).first()
    if not f or f.supprime:
        raise HTTPException(410, "Fichier indisponible")
    blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
    if not blob or not storage.blob_path(blob.checksum).exists():
        raise HTTPException(410, "Contenu indisponible")

    background = None
    if p.ephemere:
        p.telecharge = True
        p.telecharge_at = _now()
        db.commit()
        checksum, blob_id, fid, nom, pid = blob.checksum, blob.id, f.id, f.nom, p.id
        detruire = bool(getattr(f, "ephemere", False))

        def _post():
            from app.database import SessionLocal
            s = SessionLocal()
            try:
                if detruire:
                    ff = s.query(Fichier).filter(Fichier.id == fid).first()
                    if ff:
                        s.delete(ff)
                    s.query(Partage).filter(Partage.id == pid).update({"fichier_id": None})
                    s.commit()
                    if s.query(Fichier).filter(Fichier.blob_id == blob_id).count() == 0:
                        storage.delete_blob(checksum)
                        bb = s.query(FichierBlob).filter(FichierBlob.id == blob_id).first()
                        if bb:
                            s.delete(bb)
                        s.commit()
            except Exception:
                s.rollback()
            finally:
                s.close()
        background = BackgroundTask(_post)

    _audit(db, user, "download", f.id, f"téléchargement sécurisé : {f.nom}")
    headers = {"Content-Disposition": f'attachment; filename="{f.nom}"'}
    return StreamingResponse(storage.iter_blob(blob.checksum), media_type=blob.mime,
                             headers=headers, background=background)


@router.post("/envoyer")
async def envoyer_fichier(fichier_id: int = Form(...),
                          destinataires_uids: str = Form(...),   # CSV d'ids users locaux
                          ephemere: Optional[str] = Form(None),
                          message: str = Form(""),
                          db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Crée un partage RESTREINT lié aux comptes destinataires (locaux) puis
    dépose un message dans la messagerie interne de chacun, avec le lien sécurisé.
    Aucun lien à copier : l'envoi est direct vers les boîtes de réception."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fichier_id)
    if f.supprime:
        raise HTTPException(400, "Fichier en corbeille")

    uids = [int(x) for x in str(destinataires_uids or "").split(",") if x.strip().isdigit()]
    if not uids:
        raise HTTPException(400, "Aucun destinataire valide")

    # Restreint si le fichier l'exige (case à l'upload) — défaut sécurisé.
    restreint = bool(getattr(f, "download_restreint", True))
    is_eph = str(ephemere if ephemere is not None else ("1" if getattr(f, "ephemere", False) else "0")).lower() \
        in ("1", "true", "on", "oui")

    jeton = secrets.token_urlsafe(24)
    p = Partage(fichier_id=f.id, jeton=jeton, cible_type="lien", droit="lecture",
                ephemere=is_eph, restreint=restreint,
                destinataires_uids=",".join(str(u) for u in uids), created_by=user.id)
    db.add(p); db.commit(); db.refresh(p)

    url = f"/api/v1/fichiers/d/{jeton}"  # toujours via l'endpoint sécurisé
    expediteur = getattr(user, "display_name", None) or getattr(user, "username", "?")

    # Dépose un message interne par destinataire (comptes LOCAUX uniquement ici).
    sent = 0
    try:
        from plugins.messagerie.models import Message as _Msg
        from app.models import User as _User
        import datetime as _dt
        for uid in uids:
            target = db.query(_User).filter(_User.id == uid, _User.active == True).first()  # noqa: E712
            if not target:
                continue
            corps = (message.strip() + "\n\n") if message.strip() else ""
            corps += f"📁 {expediteur} vous a envoyé un fichier : [url={url}]{f.nom}[/url]"
            m = _Msg(canal="interne", direction="out",
                     expediteur_id=user.id, expediteur_nom=expediteur,
                     destinataires=[{"type": "user", "value": uid,
                                     "display": target.display_name or target.username}],
                     sujet=f"📁 Fichier partagé — {f.nom}",
                     contenu=corps, contenu_format="plain",
                     statut="sent", sent_at=_dt.datetime.now(_dt.timezone.utc))
            db.add(m); sent += 1
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Partage créé mais l'envoi des messages a échoué")

    _audit(db, user, "partage", f.id,
           f"envoyé à {sent} destinataire(s){' [restreint]' if restreint else ''}")
    return {"ok": True, "jeton": jeton, "url": url, "restreint": restreint,
            "ephemere": is_eph, "destinataires": sent}


# ── Partage EXTERNE protégé : mot de passe à usage unique envoyé par SMS ──────
# Modèle de menace : le destinataire n'a PAS de compte SCRIBE. On sépare les
# canaux — le lien circule par un canal (e-mail…), le mot de passe par un autre
# (SMS). Le serveur ne conserve QUE le hash bcrypt du mot de passe ; le mot de
# passe clair n'est jamais renvoyé, ni journalisé. Pli à usage unique, expirant,
# avec rate-limit anti-brute-force.
_PWD_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sans 0/O/1/I/L ambigus
_MAX_PLI_TENTATIVES = 5


def _gen_password(n: int = 8) -> str:
    return "".join(secrets.choice(_PWD_ALPHABET) for _ in range(n))


def _mask_phone(ph: str) -> str:
    digits = "".join(c for c in (ph or "") if c.isdigit())
    if len(digits) <= 2:
        return "••"
    return "•• •• •• •" + digits[-3:-2] + " " + digits[-2:]


async def _send_password_sms(db: Session, phone: str, password: str, file_name: str):
    """Envoie le mot de passe d'accès par SMS (canal séparé). Retourne
    (ok: bool, error: str|None). Le mot de passe n'est jamais journalisé."""
    try:
        from plugins.notifications.models import NotifChannel
        from plugins.notifications.backends.sms import SmsBackend
        from plugins.notifications.dispatcher import _apply_central_config
        import json as _json
        ch = db.query(NotifChannel).filter(NotifChannel.kind == "sms").first()
        cfg = {}
        if ch and ch.config_json:
            try:
                cfg = _json.loads(ch.config_json)
            except Exception:
                cfg = {}
        cfg = _apply_central_config("sms", cfg)
        backend = SmsBackend(cfg)
        if not backend.is_configured():
            return False, "Passerelle SMS non configurée"
        nom = (file_name or "").replace('"', "").replace("\n", " ")[:60]
        text = (f'SCRIBE - Code de telechargement pour "{nom}" : {password} '
                f'(usage unique, ne pas partager)')
        res = await backend.send_raw(text, phone)
        return bool(res.success), (None if res.success else (res.error or "Echec SMS"))
    except Exception as e:
        return False, str(e)


@router.post("/partage-protege")
async def creer_partage_protege(fichier_id: int = Form(...),
                                telephone: str = Form(...),
                                ephemere: Optional[str] = Form(None),
                                db: Session = Depends(get_db),
                                user=Depends(get_current_user)):
    """Crée un pli protégé par mot de passe (usage unique, expirant) et envoie le
    mot de passe au destinataire par SMS. Le créateur transmet le LIEN par un
    autre canal. Échec d'envoi SMS = échec du partage (rollback)."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fichier_id)
    if f.supprime:
        raise HTTPException(400, "Fichier en corbeille")
    phone = (telephone or "").strip()
    if len("".join(c for c in phone if c.isdigit())) < 6:
        raise HTTPException(400, "Numéro de mobile invalide")

    is_eph = str(ephemere if ephemere is not None else "0").lower() in ("1", "true", "on", "oui")
    password = _gen_password(8)
    jeton = secrets.token_urlsafe(24)
    p = Partage(fichier_id=f.id, jeton=jeton, cible_type="lien", droit="lecture",
                ephemere=is_eph, restreint=False, protege=True,
                mdp_hash=_hash(password), tentatives=0,
                contact_externe=_mask_phone(phone),
                expire_at=_now() + timedelta(days=7), created_by=user.id)
    db.add(p); db.commit(); db.refresh(p)

    ok, sms_err = await _send_password_sms(db, phone, password, f.nom)
    password = None  # le mot de passe clair ne survit pas à cette ligne
    if not ok:
        # Pas de pli sans mot de passe livré : on annule.
        try:
            db.delete(p); db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(502, f"Échec d'envoi du SMS — partage annulé ({sms_err})")

    _audit(db, user, "partage", f.id,
           f"pli protégé — mot de passe envoyé par SMS au {p.contact_externe}"
           + (" [éphémère]" if is_eph else ""))
    return {"ok": True, "jeton": jeton,
            "url": f"/api/v1/fichiers/pli/{jeton}",
            "telephone_masque": p.contact_externe, "ephemere": is_eph}


def _split_emails(raw: str):
    parts = []
    for chunk in (raw or "").replace(";", ",").replace(" ", ",").split(","):
        e = chunk.strip()
        if e and "@" in e and "." in e.split("@")[-1] and len(e) <= 254:
            parts.append(e)
    # déduplication en conservant l'ordre
    seen, out = set(), []
    for e in parts:
        if e.lower() not in seen:
            seen.add(e.lower()); out.append(e)
    return out


async def _send_link_mail(db: Session, emails, link: str, file_name: str):
    """Envoie le LIEN du pli par e-mail (le mot de passe N'est PAS envoyé ici :
    il est affiché à l'émetteur pour transmission par un canal séparé).
    Retourne (nb_ok: int, error: str|None)."""
    try:
        from plugins.notifications.models import NotifChannel
        from plugins.notifications.backends.mail import MailBackend
        from plugins.notifications.backends.base import NotifPayload
        from plugins.notifications.dispatcher import _apply_central_config
        import json as _json
        ch = db.query(NotifChannel).filter(NotifChannel.kind == "mail").first()
        cfg = {}
        if ch and ch.config_json:
            try:
                cfg = _json.loads(ch.config_json)
            except Exception:
                cfg = {}
        cfg = _apply_central_config("mail", cfg)
        backend = MailBackend(cfg)
        if not backend.is_configured():
            return 0, "Passerelle e-mail non configurée"
        nom = (file_name or "fichier").replace("\n", " ")[:120]
        payload = NotifPayload(
            title=f'Fichier partagé : "{nom}"',
            body=("Vous avez reçu un fichier sécurisé via SCRIBE.\n\n"
                  f"Téléchargez-le ici :\n{link}\n\n"
                  "Un mot de passe à usage unique vous est communiqué séparément "
                  "(par SMS ou un autre canal). Il vous sera demandé pour ouvrir le pli.\n\n"
                  "Lien à usage unique — ne le partagez pas."),
            urgency=2)
        ok = 0
        last_err = None
        for addr in emails:
            res = await backend.send(payload, addr)
            if res.success:
                ok += 1
            else:
                last_err = res.error or "Échec e-mail"
        return ok, (None if ok else (last_err or "Échec e-mail"))
    except Exception as e:
        return 0, str(e)


@router.post("/partage-protege-mail")
async def creer_partage_protege_mail(request: Request,
                                     fichier_id: int = Form(...),
                                     emails: str = Form(...),
                                     ephemere: Optional[str] = Form(None),
                                     db: Session = Depends(get_db),
                                     user=Depends(get_current_user)):
    """Pli protégé envoyé à un externe par E-MAIL : le LIEN part par e-mail, le
    mot de passe (généré ici) est RETOURNÉ pour être affiché à l'émetteur, qui le
    transmet par un canal séparé (SMS, téléphone…). Séparation des canaux assurée
    par l'émetteur. Échec d'envoi e-mail = échec du partage (rollback)."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    f = _get_owned(db, user, fichier_id)
    if f.supprime:
        raise HTTPException(400, "Fichier en corbeille")
    dests = _split_emails(emails)
    if not dests:
        raise HTTPException(400, "Aucune adresse e-mail valide")
    if len(dests) > 20:
        raise HTTPException(400, "Trop de destinataires (max 20)")

    is_eph = str(ephemere if ephemere is not None else "0").lower() in ("1", "true", "on", "oui")
    password = _gen_password(8)
    jeton = secrets.token_urlsafe(24)
    masque = (dests[0] if len(dests) == 1 else f"{dests[0]} (+{len(dests) - 1})")
    p = Partage(fichier_id=f.id, jeton=jeton, cible_type="lien", droit="lecture",
                ephemere=is_eph, restreint=False, protege=True,
                mdp_hash=_hash(password), tentatives=0,
                contact_externe=masque[:60],
                expire_at=_now() + timedelta(days=7), created_by=user.id)
    db.add(p); db.commit(); db.refresh(p)

    rel_url = f"/api/v1/fichiers/pli/{jeton}"
    # Lien ABSOLU pour l'e-mail externe, construit côté serveur (sûr) depuis l'hôte
    # de la requête : le pli est servi par l'instance d'origine.
    abs_url = str(request.base_url).rstrip("/") + rel_url
    ok, mail_err = await _send_link_mail(db, dests, abs_url, f.nom)
    if not ok:
        try:
            db.delete(p); db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(502, f"Échec d'envoi de l'e-mail — partage annulé ({mail_err})")

    _audit(db, user, "partage", f.id,
           f"pli protégé — lien envoyé par e-mail à {masque}"
           + (" [éphémère]" if is_eph else ""))
    # ⚠ Le mot de passe est renvoyé EN CLAIR volontairement : il doit être affiché
    # à l'émetteur pour transmission hors-bande (SMS). Il n'est jamais journalisé.
    return {"ok": True, "jeton": jeton, "url": rel_url,
            "password": password, "emails": dests, "ephemere": is_eph}


def _pli_html(jeton: str, nom: str = "", error: str = "") -> str:
    """Page autonome (hors SPA) de saisie du mot de passe d'un pli protégé."""
    safe_nom = (nom or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_jeton = "".join(c for c in (jeton or "") if c.isalnum() or c in "-_")
    err_html = ('<div class="err">' + error.replace("<", "&lt;") + "</div>") if error else ""
    titre = ('<p class="nom">📎 ' + safe_nom + "</p>") if safe_nom else ""
    disabled = "" if nom or not error else ""
    form = "" if (error and not nom) else (
        '<form method="post" action="/api/v1/fichiers/pli/' + safe_jeton + '">'
        '<label for="mdp">Mot de passe reçu par SMS</label>'
        '<input id="mdp" name="motdepasse" type="text" autocomplete="off" '
        'autocapitalize="characters" autofocus maxlength="32" '
        'placeholder="Code à 8 caractères">'
        '<button type="submit">Télécharger le fichier</button>'
        "</form>")
    return (
        "<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Pli sécurisé — SCRIBE</title><style>"
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;"
        "background:#f5f5fe;color:#161616;min-height:100vh;display:flex;"
        "align-items:center;justify-content:center;padding:20px}"
        ".card{background:#fff;border:1px solid #e5e5ed;border-radius:14px;"
        "box-shadow:0 12px 40px rgba(0,0,0,.08);max-width:420px;width:100%;padding:34px 30px}"
        ".brand{font-weight:700;font-size:20px;color:#000091;letter-spacing:.3px}"
        ".lead{color:#666;font-size:13.5px;margin:6px 0 20px}"
        ".nom{font-weight:600;font-size:14px;margin-bottom:18px;word-break:break-word}"
        "label{display:block;font-size:12px;font-weight:600;color:#666;margin-bottom:7px;"
        "text-transform:uppercase;letter-spacing:.3px}"
        "input{width:100%;padding:12px 14px;border:1px solid #d5d5e0;border-radius:8px;"
        "font-size:18px;letter-spacing:3px;text-align:center;font-weight:600}"
        "input:focus{outline:none;border-color:#000091}"
        "button{width:100%;margin-top:16px;padding:12px;background:#000091;color:#fff;"
        "border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer}"
        "button:hover{background:#00007a}"
        ".err{background:#ffe9e9;border-left:3px solid #e1000f;color:#a30009;"
        "padding:10px 12px;border-radius:6px;font-size:13px;margin-bottom:18px}"
        ".foot{margin-top:22px;font-size:11px;color:#999;text-align:center;line-height:1.5}"
        "</style></head><body><div class=\"card\">"
        "<div class=\"brand\">SCRIBE</div>"
        "<p class=\"lead\">Pli sécurisé. Saisissez le mot de passe reçu par SMS "
        "pour télécharger le fichier.</p>"
        + titre + err_html + form +
        "<div class=\"foot\">Lien à usage unique. Ne partagez pas ce mot de passe. "
        "Plateforme souveraine de gestion de crise.</div>"
        "</div></body></html>")


def _pli_lookup(db: Session, jeton: str):
    """Retourne (partage, fichier, erreur, code). erreur non vide ⇒ bloquer."""
    p = db.query(Partage).filter(Partage.jeton == jeton, Partage.protege == True).first()  # noqa: E712
    if not p:
        return None, None, "Lien inconnu ou expiré.", 404
    if p.expire_at:
        _exp = p.expire_at
        _ref = _now() if _exp.tzinfo is not None else _now().replace(tzinfo=None)
        if _exp < _ref:
            return p, None, "Ce pli a expiré.", 410
    if p.telecharge:
        return p, None, "Ce pli a déjà été téléchargé.", 410
    if (p.tentatives or 0) >= _MAX_PLI_TENTATIVES:
        return p, None, "Trop de tentatives. Pli verrouillé pour des raisons de sécurité.", 429
    f = db.query(Fichier).filter(Fichier.id == p.fichier_id).first()
    if not f or f.supprime:
        return p, None, "Fichier indisponible.", 410
    return p, f, "", 200


@router.get("/pli/{jeton}", response_class=HTMLResponse)
def page_pli(jeton: str, db: Session = Depends(get_db)):
    p, f, erreur, code = _pli_lookup(db, jeton)
    if erreur:
        return HTMLResponse(_pli_html(jeton, error=erreur), status_code=code)
    return HTMLResponse(_pli_html(jeton, nom=f.nom))


@router.post("/pli/{jeton}", response_class=HTMLResponse)
def ouvrir_pli(jeton: str, motdepasse: str = Form(""), db: Session = Depends(get_db)):
    p, f, erreur, code = _pli_lookup(db, jeton)
    if erreur:
        return HTMLResponse(_pli_html(jeton, error=erreur), status_code=code)
    if not _verify(motdepasse or "", p.mdp_hash or ""):
        p.tentatives = (p.tentatives or 0) + 1
        db.commit()
        reste = max(0, _MAX_PLI_TENTATIVES - p.tentatives)
        msg = ("Mot de passe incorrect. " +
               (f"{reste} tentative(s) restante(s)." if reste
                else "Pli verrouillé pour des raisons de sécurité."))
        return HTMLResponse(_pli_html(jeton, nom=(f.nom if reste else ""), error=msg),
                            status_code=403 if reste else 429)
    blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
    if not blob or not storage.blob_path(blob.checksum).exists():
        return HTMLResponse(_pli_html(jeton, error="Contenu indisponible."), status_code=410)

    # Succès : pli consommé (usage unique). Le mot de passe n'est PAS journalisé.
    p.tentatives = 0
    p.telecharge = True
    p.telecharge_at = _now()
    db.add(JournalFichier(action="partage", fichier_id=f.id,
                          acteur="pli protégé", acteur_role="",
                          horodatage=_now(),
                          details=f"téléchargé via pli protégé ({p.contact_externe})"))
    db.commit()

    checksum = blob.checksum
    blob_id = blob.id
    fid = f.id
    detruire = bool(getattr(f, "ephemere", False))

    def _purge_si_ephemere():
        if not detruire:
            return
        from app.database import SessionLocal
        s = SessionLocal()
        try:
            ff = s.query(Fichier).filter(Fichier.id == fid).first()
            if ff:
                s.delete(ff)
            s.query(Partage).filter(Partage.fichier_id == fid).update({"fichier_id": None})
            s.commit()
            if s.query(Fichier).filter(Fichier.blob_id == blob_id).count() == 0:
                storage.delete_blob(checksum)
                bb = s.query(FichierBlob).filter(FichierBlob.id == blob_id).first()
                if bb:
                    s.delete(bb)
                s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()

    headers = {"Content-Disposition": f'attachment; filename="{f.nom}"'}
    return StreamingResponse(storage.iter_blob(checksum), media_type=blob.mime,
                             headers=headers, background=BackgroundTask(_purge_si_ephemere))


@router.get("/partages")
def list_partages(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """« Partagé avec moi » : partages REÇUS — ceux où l'utilisateur connecté
    figure dans les destinataires. (Auparavant : partages ENVOYÉS, d'où la
    section vide côté destinataire.) Chaque entrée porte son dossier de rangement
    éventuel (organisation personnelle du destinataire) et l'expéditeur."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    from app.models import User as _User
    rang = {r.partage_id: r.dossier_id
            for r in db.query(PartageRangement).filter(PartageRangement.uid == user.id).all()}
    out = []
    shares = (db.query(Partage)
                .filter(Partage.destinataires_uids != "")
                .order_by(Partage.created_at.desc()).all())
    for p in shares:
        uids = {int(x) for x in (p.destinataires_uids or "").split(",") if x.strip().isdigit()}
        if user.id not in uids:
            continue
        f = db.query(Fichier).filter(Fichier.id == p.fichier_id).first()
        eph = bool(p.ephemere)
        exp = db.query(_User).filter(_User.id == p.created_by).first() if p.created_by else None
        out.append({
            "id": p.id, "jeton": p.jeton, "nom": f.nom if f else "—",
            "ephemere": eph,
            "url": f"/api/v1/fichiers/{'e' if eph else 'p'}/{p.jeton}",
            "telecharge": bool(p.telecharge),
            "telecharge_at": p.telecharge_at.isoformat() if p.telecharge_at else None,
            "actif": (f is not None and not f.supprime) and (not eph or not p.telecharge),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "expediteur": (exp.display_name or exp.username) if exp else "—",
            "dossier_dest_id": rang.get(p.id),
            "external": False,
        })
    # Partages REÇUS d'une AUTRE instance (fédérés) : ils n'ont pas de Partage
    # local — le fichier vit sur l'instance émettrice et nous est parvenu via un
    # message interne fédéré porteur d'un lien ABSOLU. On les fait apparaître ici
    # (téléchargement via le lien d'origine ; non rangeables en dossier).
    out.extend(_federated_received_shares(db, user))
    return out


def _federated_received_shares(db, user) -> list:
    out = []
    try:
        import re as _re
        from plugins.messagerie.models import Message as _Msg
        msgs = (db.query(_Msg)
                  .filter(_Msg.direction == "in")
                  .filter(_Msg.contenu.like("%[url=http%/api/v1/fichiers/%"))
                  .order_by(_Msg.created_at.desc()).limit(300).all())
        seen = set()
        for m in msgs:
            mine = any((d or {}).get("type") == "user" and str((d or {}).get("value")) == str(user.id)
                       for d in (m.destinataires or []))
            if not mine:
                continue
            mt = _re.search(r"\[url=(https?://[^\]]+/api/v1/fichiers/[^\]]+)\]([^\[]+)\[/url\]",
                            m.contenu or "")
            if not mt:
                continue
            url, nom = mt.group(1), mt.group(2).strip()
            if url in seen:
                continue
            seen.add(url)
            out.append({
                "id": "fed-%d" % m.id, "jeton": "", "nom": nom,
                "ephemere": False, "url": url, "external": True, "federe": True,
                "telecharge": False, "actif": True,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "expediteur": m.expediteur_nom or "—",
                "dossier_dest_id": None,
            })
    except Exception:
        pass
    return out


# ── « Partagé avec moi » : dossiers d'organisation du destinataire ───────────
@router.get("/partages-dossiers")
def list_partages_dossiers(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    folders = (db.query(Dossier)
                 .filter(Dossier.proprietaire_id == user.id, Dossier.type == "partage_recu")
                 .order_by(Dossier.nom).all())
    # compteur de partages rangés par dossier
    counts = {}
    for r in db.query(PartageRangement).filter(PartageRangement.uid == user.id).all():
        counts[r.dossier_id] = counts.get(r.dossier_id, 0) + 1
    return [{"id": d.id, "nom": d.nom, "count": counts.get(d.id, 0)} for d in folders]


@router.post("/partages-dossiers")
def creer_partage_dossier(nom: str = Form(...), db: Session = Depends(get_db),
                          user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    nom = (nom or "").strip()[:255]
    if not nom:
        raise HTTPException(400, "Nom requis")
    d = Dossier(nom=nom, proprietaire_id=user.id, type="partage_recu")
    db.add(d); db.commit(); db.refresh(d)
    return {"id": d.id, "nom": d.nom, "count": 0}


@router.put("/partages-dossiers/{did}")
def renommer_partage_dossier(did: int, nom: str = Form(...),
                             db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    d = (db.query(Dossier)
           .filter(Dossier.id == did, Dossier.proprietaire_id == user.id,
                   Dossier.type == "partage_recu").first())
    if not d:
        raise HTTPException(404, "Dossier introuvable")
    nom = (nom or "").strip()[:255]
    if nom:
        d.nom = nom
        db.commit()
    return {"ok": True, "nom": d.nom}


@router.delete("/partages-dossiers/{did}")
def supprimer_partage_dossier(did: int, db: Session = Depends(get_db),
                              user=Depends(get_current_user)):
    """Supprime un dossier d'organisation. Les partages qu'il contenait reviennent
    à la RACINE de « Partagé avec moi » (on ne supprime que les rangements, jamais
    les fichiers eux-mêmes)."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    d = (db.query(Dossier)
           .filter(Dossier.id == did, Dossier.proprietaire_id == user.id,
                   Dossier.type == "partage_recu").first())
    if not d:
        raise HTTPException(404, "Dossier introuvable")
    db.query(PartageRangement).filter(
        PartageRangement.uid == user.id, PartageRangement.dossier_id == did).delete()
    db.delete(d); db.commit()
    return {"ok": True}


@router.post("/partages/{pid}/ranger")
def ranger_partage(pid: int, dossier_id: Optional[int] = Form(None),
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Range un partage REÇU dans un dossier d'organisation (ou le ramène à la
    racine si dossier_id est vide). Réservé aux destinataires du partage."""
    if not user:
        raise HTTPException(401, "Non autorisé")
    p = db.query(Partage).filter(Partage.id == pid).first()
    if not p:
        raise HTTPException(404, "Partage introuvable")
    uids = {int(x) for x in (p.destinataires_uids or "").split(",") if x.strip().isdigit()}
    if user.id not in uids:
        raise HTTPException(403, "Partage non reçu par cet utilisateur")
    db.query(PartageRangement).filter(
        PartageRangement.uid == user.id, PartageRangement.partage_id == pid).delete()
    if dossier_id:
        d = (db.query(Dossier)
               .filter(Dossier.id == dossier_id, Dossier.proprietaire_id == user.id,
                       Dossier.type == "partage_recu").first())
        if not d:
            raise HTTPException(404, "Dossier introuvable")
        db.add(PartageRangement(partage_id=pid, uid=user.id, dossier_id=dossier_id))
    db.commit()
    return {"ok": True}


@router.delete("/partage/{pid}")
def revoquer_partage(pid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    p = db.query(Partage).filter(Partage.id == pid, Partage.created_by == user.id).first()
    if not p:
        raise HTTPException(404, "Partage introuvable")
    db.delete(p); db.commit()
    return {"ok": True}


@router.get("/e/{jeton}")
def consommer_ephemere(jeton: str, db: Session = Depends(get_db)):
    """Consomme un lien éphémère : délivre le fichier puis l'efface.

    Auth : le JETON lui-même fait foi (capability-URL à usage unique,
    ~192 bits, non devinable). Le lien est donc directement cliquable dans le
    navigateur, sans en-tête d'authentification. « Interne » au sens réseau de
    l'instance : à ne pas exposer hors du périmètre.

    Atomicité : on marque le partage consommé EN BASE avant de streamer ; un
    second appel concurrent voit ``telecharge=True`` et reçoit 410 Gone. La
    suppression du fichier + purge du blob est faite en tâche d'arrière-plan,
    une fois la réponse intégralement envoyée.
    """
    p = db.query(Partage).filter(Partage.jeton == jeton, Partage.ephemere == True).first()  # noqa: E712
    if not p:
        raise HTTPException(404, "Lien inconnu")
    if p.telecharge:
        raise HTTPException(410, "Lien déjà utilisé")
    if p.expire_at and p.expire_at < _now():
        raise HTTPException(410, "Lien expiré")
    f = db.query(Fichier).filter(Fichier.id == p.fichier_id).first()
    if not f or f.supprime:
        raise HTTPException(410, "Fichier indisponible")
    blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
    if not blob or not storage.blob_path(blob.checksum).exists():
        raise HTTPException(410, "Contenu indisponible")

    # Marquage atomique « consommé » AVANT le stream (anti double-téléchargement)
    p.telecharge = True
    p.telecharge_at = _now()
    db.commit()

    checksum = blob.checksum
    blob_id = blob.id
    fid = f.id
    nom = f.nom
    pid = p.id
    # Le fichier ne s'auto-détruit QUE s'il a été marqué éphémère à l'upload.
    # Un fichier permanent reste dans le drive : seul le lien est consommé.
    detruire_fichier = bool(getattr(f, "ephemere", False))

    def _effacer_apres_envoi():
        # Nouvelle session : la requête est déjà terminée côté FastAPI.
        from app.database import SessionLocal
        s = SessionLocal()
        try:
            if detruire_fichier:
                ff = s.query(Fichier).filter(Fichier.id == fid).first()
                if ff:
                    s.delete(ff)
                s.query(Partage).filter(Partage.id == pid).update({"fichier_id": None})
                s.commit()
                # Purge du blob s'il n'est plus référencé
                still = s.query(Fichier).filter(Fichier.blob_id == blob_id).count()
                if still == 0:
                    storage.delete_blob(checksum)
                    bb = s.query(FichierBlob).filter(FichierBlob.id == blob_id).first()
                    if bb:
                        s.delete(bb)
                    s.commit()
                detail = f"téléchargé puis effacé (éphémère) : {nom}"
            else:
                detail = f"lien éphémère consommé (fichier conservé) : {nom}"
            s.add(JournalFichier(action="ephemere", fichier_id=None,
                                 acteur="lien éphémère", acteur_role="",
                                 horodatage=_now(), details=detail))
            s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()

    headers = {"Content-Disposition": f'attachment; filename="{nom}"'}
    return StreamingResponse(storage.iter_blob(checksum), media_type=blob.mime,
                             headers=headers, background=BackgroundTask(_effacer_apres_envoi))


# ── Quota / état drive ───────────────────────────────────────────────────────
@router.get("/quota")
def get_quota(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Non autorisé")
    total = 0
    for f in db.query(Fichier).filter(Fichier.proprietaire_id == user.id,
                                      Fichier.supprime == False).all():  # noqa: E712
        blob = db.query(FichierBlob).filter(FichierBlob.id == f.blob_id).first()
        if blob:
            total += blob.taille or 0
    return {"utilise": total, "max_fichier": MAX_FILE_BYTES}


# ── Configuration admin du plugin (carte ⚙ Plugins) ─────────────────────────
# Politique d'upload LOCALE du drive : poids max par fichier + types de fichiers
# autorisés (catégories MIME). Repli sur la politique centrale 'uploads'.
@router.get("/admin/config")
def fichiers_admin_config_get(admin=Depends(require_admin)):
    from app.plugin_settings import get_plugin_config, categories_meta
    return {"config": get_plugin_config("fichiers"), "categories": categories_meta()}


@router.post("/admin/config")
def fichiers_admin_config_post(payload: dict, admin=Depends(require_admin)):
    from app.plugin_settings import set_plugin_config
    cfg = set_plugin_config("fichiers", payload or {})
    return {"ok": True, "config": cfg}
