"""
api/attachments.py — Upload de pièces jointes liées à un incident.
v2.0.0 : validation type MIME, taille max, sanitisation du nom (path traversal).
"""
import os, shutil, re
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SitrepEntry, Attachment
from app.api.auth import get_current_user

router = APIRouter()

UPLOAD_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Types MIME autorisés (pas d'exécutables)
ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain", "text/csv",
    "application/zip",
}
MAX_UPLOAD_MB = int(os.getenv("SCRIBE_MAX_UPLOAD_MB", "10"))

def _safe_filename(incident_id: int, original: str) -> str:
    """Sanitise le nom de fichier : supprime path traversal et caractères dangereux."""
    # Ne garder que le nom de fichier (pas de chemin)
    name = Path(original).name
    # Supprimer les caractères non autorisés
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    # Éviter les noms commençant par un point
    name = name.lstrip(".")
    # Limiter la longueur
    stem = Path(name).stem[:60]
    suffix = Path(name).suffix[:10]
    return f"{incident_id}_{stem}{suffix}" or f"{incident_id}_file"


@router.post("/{incident_id}/upload")
async def upload_document(
    incident_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentification requise")
    incident = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    # Validation type MIME
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400,
            detail=f"Type de fichier non autorisé : {file.content_type}")
    # Lire et valider la taille
    content = await file.read()
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413,
            detail=f"Fichier trop volumineux (max {MAX_UPLOAD_MB} Mo)")
    # Nom sécurisé + écriture
    safe_name = _safe_filename(incident_id, file.filename or "upload")
    file_path = UPLOAD_DIR / safe_name
    # Vérifier que le chemin final est bien dans UPLOAD_DIR (double sécurité)
    if not str(file_path.resolve()).startswith(str(UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Nom de fichier invalide")
    file_path.write_bytes(content)
    attachment = Attachment(filename=file.filename, file_path=str(file_path), entry_id=incident_id)
    db.add(attachment)
    db.commit()
    return {"status": "ok", "filename": file.filename, "url": f"/uploads/{safe_name}"}


@router.get("/{incident_id}")
def get_attachments(incident_id: int, db: Session = Depends(get_db)):
    return db.query(Attachment).filter(Attachment.entry_id == incident_id).all()
