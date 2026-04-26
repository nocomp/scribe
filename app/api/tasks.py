"""
api/tasks.py — Kanban de tâches SCRIBE v5
Colonnes : BACKLOG | EN_COURS | EN_ATTENTE | TERMINÉ
"""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import Task, Notification, User

router = APIRouter()

COLONNES = ["BACKLOG", "EN_COURS", "EN_ATTENTE", "TERMINÉ"]

class TaskCreate(BaseModel):
    titre:       str
    description: Optional[str] = ""
    assignee:    Optional[str] = None
    priorite:    int = 2
    colonne:     str = "BACKLOG"
    incident_id: Optional[int] = None
    due_at:      Optional[datetime] = None

class TaskMove(BaseModel):
    colonne: str

class TaskUpdate(BaseModel):
    titre:       Optional[str] = None
    description: Optional[str] = None
    assignee:    Optional[str] = None
    priorite:    Optional[int] = None
    due_at:      Optional[datetime] = None

class TaskOut(BaseModel):
    id: int; titre: str; description: Optional[str]
    assignee: Optional[str]; priorite: int; colonne: str
    incident_id: Optional[int]
    due_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config: from_attributes = True


@router.get("/", response_model=List[TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(Task).order_by(Task.priorite.desc(), Task.created_at.asc()).all()

@router.post("/", response_model=TaskOut)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    t = Task(**body.dict())
    db.add(t); db.commit(); db.refresh(t)
    # Notifier l'assigné si renseigné
    if body.assignee:
        user = db.query(User).filter(User.username == body.assignee, User.active == True).first()
        if user:
            notif = Notification(
                user_id=user.id,
                titre=f"Tâche assignée : {body.titre}",
                message=body.description or body.titre,
                type_notif="TACHE",
                task_id=t.id,
                incident_id=body.incident_id
            )
            db.add(notif); db.commit()
    return t

@router.put("/{tid}/move")
def move_task(tid: int, body: TaskMove, db: Session = Depends(get_db)):
    if body.colonne not in COLONNES:
        raise HTTPException(400, f"Colonne invalide. Valeurs: {COLONNES}")
    t = db.query(Task).filter(Task.id == tid).first()
    if not t: raise HTTPException(404, "Tâche non trouvée")
    t.colonne = body.colonne
    t.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok", "colonne": t.colonne}

@router.put("/{tid}", response_model=TaskOut)
def update_task(tid: int, body: TaskUpdate, db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == tid).first()
    if not t: raise HTTPException(404, "Tâche non trouvée")
    old_assignee = t.assignee
    for k, v in body.dict(exclude_none=True).items():
        setattr(t, k, v)
    t.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(t)
    # Notifier si réassignation
    if body.assignee and body.assignee != old_assignee:
        user = db.query(User).filter(User.username == body.assignee, User.active == True).first()
        if user:
            notif = Notification(user_id=user.id, titre=f"Tâche réassignée : {t.titre}",
                                 message=t.description or t.titre, type_notif="TACHE", task_id=t.id)
            db.add(notif); db.commit()
    return t

@router.delete("/{tid}")
def delete_task(tid: int, db: Session = Depends(get_db)):
    t = db.query(Task).filter(Task.id == tid).first()
    if not t: raise HTTPException(404, "Tâche non trouvée")
    db.delete(t); db.commit()
    return {"status": "deleted"}
