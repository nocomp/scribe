"""plugins/chat/sync.py — Synchronisation inter-GHT via collecteur"""
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import get_current_user
from plugins.chat.models import ChatMessage, ChatSalon

sync_router = APIRouter()


class SyncMessageIn(BaseModel):
    salon_nom:    str
    auteur_nom:   str
    auteur_sigle: str
    contenu:      str
    mentions:     list = []
    horodatage:   Optional[str] = None


@sync_router.post("/push")
def push_message(body: SyncMessageIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Reçoit un message inter-GHT depuis le collecteur et l'injecte dans le salon correspondant."""
    if not user: raise HTTPException(401)

    # Trouver ou ignorer le salon territorial
    salon = db.query(ChatSalon).filter(
        ChatSalon.nom == body.salon_nom,
        ChatSalon.type == "territorial",
        ChatSalon.archive == False
    ).first()
    if not salon:
        return {"ok": False, "detail": "Salon territorial non trouvé"}

    # Éviter les doublons (même auteur_sigle + même contenu dans la même seconde)
    recent = db.query(ChatMessage).filter(
        ChatMessage.salon_id == salon.id,
        ChatMessage.auteur_sigle == body.auteur_sigle,
        ChatMessage.contenu == body.contenu,
        ChatMessage.origine == "ght"
    ).order_by(ChatMessage.id.desc()).first()
    if recent:
        delta = (datetime.now(timezone.utc) - recent.horodatage.replace(tzinfo=timezone.utc)).total_seconds()
        if delta < 10:
            return {"ok": True, "detail": "Doublon ignoré"}

    msg = ChatMessage(
        salon_id    = salon.id,
        auteur_id   = None,
        auteur_nom  = body.auteur_nom,
        auteur_sigle= body.auteur_sigle,
        contenu     = body.contenu,
        mentions    = json.dumps(body.mentions),
        origine     = "ght",
        horodatage  = datetime.now(timezone.utc),
    )
    db.add(msg); db.commit()
    return {"ok": True}


@sync_router.get("/pull")
def pull_messages(since_id: int = 0, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Retourne les messages territoriaux depuis un ID donné (pour push vers collecteur)."""
    if not user: raise HTTPException(401)
    msgs = db.query(ChatMessage).join(
        ChatSalon, ChatMessage.salon_id == ChatSalon.id
    ).filter(
        ChatSalon.type == "territorial",
        ChatMessage.id > since_id,
        ChatMessage.origine == "local",
        ChatMessage.supprime == False,
    ).order_by(ChatMessage.id).limit(50).all()

    from plugins.chat.routes import _fmt_message
    return [_fmt_message(m, db) for m in msgs]
