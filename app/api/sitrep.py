"""
api/sitrep.py — Main courante complète v2.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .v140 import _log_mc
from sqlalchemy import func as sqlfunc
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel
import json

from app.database import get_db
from app.models import SitrepEntry, Attachment
try:
    from app.api.auth import notify_incident, get_current_user, require_user
except Exception:
    def notify_incident(db, incident, action='INCIDENT'): pass
    def get_current_user(): pass
    def require_user(): pass

router = APIRouter()


class IncidentCreate(BaseModel):
    declarant_nom: str
    directeur_crise: Optional[str] = None
    site_id: str
    unite_fonctionnelle: Optional[str] = ""
    type_crise: Optional[str] = "CYBER"
    urgency: int = 1
    fait: str
    analyse: Optional[str] = ""
    moyens_engages: Optional[str] = ""
    actions_remediation: Optional[str] = ""
    intervenant_nom: Optional[str] = ""
    intervenant_contact: Optional[str] = ""
    estimated_resolution: Optional[datetime] = None
    # v2182 : panne opérationnelle (respirateur HS, DPI down, etc.) vs événement clinique
    impact_fonctionnel: Optional[bool] = False
    # v3.4 (h34) : expose l'incident au personnel soignant (brancardiers, IDE coordo)
    # Cocher pour les pannes qui impactent l'activité soignante : DPI HS,
    # ascenseur, équipement médical, indisponibilité service.
    visible_soignant: Optional[bool] = False
    # Jalons prédéfinis (liste de labels)
    jalons_labels: Optional[List[str]] = []

class IncidentOut(BaseModel):
    id: int
    timestamp: datetime
    declarant_nom: str
    directeur_crise: Optional[str]
    site_id: str
    unite_fonctionnelle: Optional[str]
    type_crise: str
    urgency: int
    fait: str
    analyse: Optional[str]
    moyens_engages: Optional[str]
    actions_remediation: Optional[str]
    intervenant_nom: Optional[str]
    intervenant_contact: Optional[str]
    status: str
    completion_percent: int
    estimated_resolution: Optional[datetime]
    resolved_at: Optional[datetime]
    jalons: Optional[str]
    albert_avis: Optional[str]
    impact_fonctionnel: Optional[bool] = False
    visible_soignant: Optional[bool] = False  # v3.4 (h34)
    class Config:
        from_attributes = True
        # v2.3.88 — Les datetimes SQLite sont naïves mais stockées en UTC
        # (func.now() sur SQLite = UTC). Pydantic les sérialise sans 'Z',
        # ce qui fait que le navigateur les interprète comme heure locale
        # → décalage de 2h en été (Europe/Paris = UTC+2).
        # Ce serializer force le suffix 'Z' pour forcer l'interprétation UTC
        # côté client, cohérent avec parseUTC(...) dans scribe.js.
        @staticmethod
        def json_encoders():
            return {datetime: lambda v: v.isoformat() + ('Z' if v.tzinfo is None else '')}
        json_encoders = {
            datetime: lambda v: (v.isoformat() + 'Z') if v.tzinfo is None else v.isoformat()
        }

class StatusUpdate(BaseModel):
    status: str
    completion_percent: Optional[int] = None

class JalonUpdate(BaseModel):
    jalons: List[dict]  # [{label, done, done_at}]

class AlbertAvisUpdate(BaseModel):
    avis: str


@router.post("/post", response_model=IncidentOut)
def create_incident(entry: IncidentCreate, request: Request, db: Session = Depends(get_db)):
    data = entry.dict(exclude={"jalons_labels"})
    # Construire les jalons depuis les labels
    jalons_labels = entry.jalons_labels or []
    if jalons_labels:
        jalons = [{"label": l, "done": False, "done_at": None} for l in jalons_labels]
        data["jalons"] = json.dumps(jalons, ensure_ascii=False)
    new_incident = SitrepEntry(**data)
    db.add(new_incident)
    db.flush()
    _log_mc(db, None, "INCIDENT", "DÉCLARÉ",
        f"[UF:{entry.unite_fonctionnelle}] {entry.fait[:80]}",
        ref_id=new_incident.id, niveau="WARN" if entry.urgency >= 3 else "INFO")
    db.commit()
    db.refresh(new_incident)
    try:
        notify_incident(db, new_incident)
    except Exception:
        pass
    # v2.3.87 — Plugin notifications multi-canal (mail/push/SMS).
    # Fail-safe : une erreur n'empêche jamais la création de l'incident.
    try:
        from plugins.notifications.dispatcher import notify_sync
        notify_sync(
            event_type="incident_created",
            title=f"[{new_incident.site_id or '?'}] {entry.fait[:100]}",
            body=(entry.analyse or entry.fait or "")[:500],
            urgency=int(entry.urgency or 2),
            context={
                "incident_id": new_incident.id,
                "uf": entry.unite_fonctionnelle or "",
                "url": f"/#incidents/{new_incident.id}",
                # h74 — URL publique (déduite de la requête) pour bâtir un lien SMS absolu
                "base_url": str(request.base_url).rstrip("/"),
                "type_crise": entry.type_crise or "",
            },
        )
    except Exception:
        pass
    # v3.0.0 — Hook tuteur backend : observer la création d'incident côté serveur,
    # pas seulement depuis le navigateur joueur. Indispensable pour que l'Assistant
    # détecte les incidents injectés par stimuli (qui n'ont aucun navigateur dans
    # la boucle). Fail-safe : une erreur n'empêche jamais la création de l'incident.
    try:
        from plugins.tuteur.backend_observer import observe_backend
        observe_backend(
            db=db,
            type_observation="INCIDENT_CREE",
            target_type="incident",
            target_id=new_incident.id,
            detail={
                "fait":       (entry.fait or "")[:120],
                "urgency":    int(entry.urgency or 2),
                "type_crise": (entry.type_crise or "")[:60],
                "source":     "api",  # vs "stimulus_collecteur"
            },
        )
    except Exception:
        pass
    return new_incident


@router.get("/history", response_model=List[IncidentOut])
def get_history(
    site: Optional[str] = None,
    urgency: Optional[int] = None,
    status: Optional[str] = None,
    type_crise: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    """
    Liste les incidents.

    v3.4 (h34) — Filtrage RGPD selon le rôle :
    - admin, cellule_crise : voient tous les incidents (comportement historique).
    - soignant : voit uniquement les incidents tels que :
        * visible_soignant=True (exposés explicitement par la cellule de crise), OU
        * il existe une Task assignée à l'utilisateur sur cet incident, OU
        * il existe une BrancardageMission liée à cet incident dont
          l'agent est l'utilisateur.
    - autres rôles (ou non authentifié) : tableau vide (sécurité par défaut).

    Cette projection limite l'exposition de données dont le soignant n'a pas
    besoin opérationnellement, conformément au principe de minimisation RGPD.
    """
    q = db.query(SitrepEntry)
    if site:       q = q.filter(SitrepEntry.site_id == site)
    if urgency:    q = q.filter(SitrepEntry.urgency == urgency)
    if status:     q = q.filter(SitrepEntry.status == status)
    if type_crise: q = q.filter(SitrepEntry.type_crise == type_crise)

    # Filtrage selon rôle
    role = (user.role if user else "") or ""
    if role in ("admin", "cellule_crise"):
        # Accès complet (comportement historique)
        return q.order_by(SitrepEntry.timestamp.desc()).all()

    if role == "soignant":
        from sqlalchemy import or_, exists
        from app.models import Task
        try:
            from plugins.brancardage.models import BrcMission
            has_branc = True
        except Exception:
            has_branc = False
        # Condition 1 : visible_soignant=True
        cond_visible = SitrepEntry.visible_soignant == True  # noqa: E712
        # Condition 2 : tâche assignée à l'utilisateur
        cond_task = exists().where(
            (Task.incident_id == SitrepEntry.id) &
            (Task.assignee == user.username)
        )
        conditions = [cond_visible, cond_task]
        # Condition 3 (optionnelle) : mission de brancardage liée
        if has_branc and hasattr(BrcMission, "incident_id"):
            cond_branc = exists().where(
                (BrcMission.incident_id == SitrepEntry.id) &
                (BrcMission.agent_nom == user.display_name)
            )
            conditions.append(cond_branc)
        q = q.filter(or_(*conditions))
        return q.order_by(SitrepEntry.timestamp.desc()).all()

    # Rôle inconnu ou non authentifié : aucun incident
    return []


@router.put("/{incident_id}/status")
def update_status(incident_id: int, update: StatusUpdate, db: Session = Depends(get_db)):
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    inc.status = update.status
    if update.completion_percent is not None:
        inc.completion_percent = update.completion_percent
    _log_mc(db, None, "INCIDENT", f"STATUT→{update.status}",
        f"Incident #{incident_id} : {inc.fait[:60] if inc.fait else ''}", ref_id=incident_id,
        niveau="INFO" if update.status not in ("RÉSOLU","ARCHIVÉ") else "INFO")
    # h76 — Notifier par mail les abonnés à cet incident du changement d'état.
    _email_incident_subscribers(db, inc, update.status)
    if update.status == "ARCHIVÉ":
        inc.status = "ARCHIVÉ"
        db.commit()
        return {"status": "updated", "new_status": "ARCHIVÉ"}
    if update.status == "RÉSOLU" and not inc.resolved_at:
        # Vérifier qu'au moins un jalon a été acquitté
        import json as _json
        jalons_raw = inc.jalons
        if jalons_raw:
            try:
                jalons_list = _json.loads(jalons_raw)
                if isinstance(jalons_list, list) and len(jalons_list) > 0:
                    any_done = any(j.get("done") for j in jalons_list)
                    if not any_done:
                        raise HTTPException(
                            status_code=400,
                            detail="Au moins un jalon doit être validé avant de résoudre cet incident."
                        )
            except HTTPException:
                raise
            except Exception:
                pass  # Pas de jalons structurés — on laisse passer
        inc.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "updated", "new_status": inc.status, "resolved_at": inc.resolved_at}


@router.put("/{incident_id}/archive")
def archive_incident(incident_id: int, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    """Archive un incident RÉSOLU — disparaît de la vue principale."""
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    if inc.status != "RÉSOLU":
        raise HTTPException(status_code=400, detail="Seul un incident RÉSOLU peut être archivé")
    from datetime import datetime, timezone
    inc.archived    = True
    inc.archived_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "archived_at": inc.archived_at.isoformat()}


@router.put("/{incident_id}/jalons")
def update_jalons(incident_id: int, update: JalonUpdate, db: Session = Depends(get_db)):
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    inc.jalons = json.dumps(update.jalons, ensure_ascii=False, default=str)
    # Auto-calcul completion
    total = len(update.jalons)
    done  = sum(1 for j in update.jalons if j.get("done"))
    inc.completion_percent = int(done / total * 100) if total else 0
    db.commit()
    return {"status": "ok", "completion": inc.completion_percent}


@router.put("/{incident_id}/albert-avis")
def save_albert_avis(incident_id: int, update: AlbertAvisUpdate, db: Session = Depends(get_db)):
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    inc.albert_avis = update.avis
    db.commit()
    return {"status": "ok"}


class UFUpdate(BaseModel):
    unite_fonctionnelle: str  # codes séparés par virgule, ex: "USI, REA" ou "" pour vider


@router.put("/{incident_id}/uf")
def update_uf(incident_id: int, update: UFUpdate, db: Session = Depends(get_db),
              current_user=Depends(get_current_user)):
    """Modifier les unités fonctionnelles d'un incident existant. Loggé en main courante."""
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    old_uf = inc.unite_fonctionnelle or ""
    new_uf = update.unite_fonctionnelle.strip()
    inc.unite_fonctionnelle = new_uf
    # Log en main courante
    log_detail = f"Incident #{incident_id} — UF : [{old_uf}] → [{new_uf}]"
    _log_mc(db, current_user, "INCIDENT", "UF→MODIFIÉE", log_detail,
            ref_id=incident_id, niveau="INFO")
    db.commit()
    db.refresh(inc)
    return {"status": "ok", "unite_fonctionnelle": inc.unite_fonctionnelle}


@router.delete("/{incident_id}")
def delete_incident(incident_id: int, db: Session = Depends(get_db)):
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    db.delete(inc)
    db.commit()
    return {"status": "deleted"}


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total     = db.query(SitrepEntry).count()
    critical  = db.query(SitrepEntry).filter(SitrepEntry.urgency >= 3, SitrepEntry.status != "RÉSOLU").count()
    ouverts   = db.query(SitrepEntry).filter(SitrepEntry.status != "RÉSOLU").count()
    cyber     = db.query(SitrepEntry).filter(SitrepEntry.type_crise == "CYBER").count()
    sanitaire = db.query(SitrepEntry).filter(SitrepEntry.type_crise == "SANITAIRE").count()

    by_site = db.query(
        SitrepEntry.site_id,
        sqlfunc.count(SitrepEntry.id).label("count")
    ).filter(SitrepEntry.status != "RÉSOLU").group_by(SitrepEntry.site_id).all()

    return {
        "total": total, "critical": critical, "ouverts": ouverts,
        "cyber": cyber, "sanitaire": sanitaire,
        "by_site": [{"site": r.site_id, "count": r.count} for r in by_site]
    }


@router.get("/export-csv")
def export_csv(db: Session = Depends(get_db)):
    """Export de la main courante en CSV."""
    from fastapi.responses import StreamingResponse
    import csv, io
    incidents = db.query(SitrepEntry).order_by(SitrepEntry.timestamp.asc()).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)
    writer.writerow([
        "ID","Horodatage","Type","Urgence","Site","UF","Déclarant","Directeur",
        "Fait","Analyse","Moyens","Intervenant","Contact","Statut","Résolu le","Actions"
    ])
    for i in incidents:
        writer.writerow([
            i.id,
            i.timestamp.strftime("%d/%m/%Y %H:%M:%S") if i.timestamp else "",
            i.type_crise, i.urgency, i.site_id, i.unite_fonctionnelle or "",
            i.declarant_nom, i.directeur_crise or "",
            i.fait, i.analyse or "", i.moyens_engages or "",
            i.intervenant_nom or "", i.intervenant_contact or "",
            i.status,
            i.resolved_at.strftime("%d/%m/%Y %H:%M:%S") if i.resolved_at else "",
            i.actions_remediation or ""
        ])
    output.seek(0)
    filename = f"main_courante_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── h76 — Abonnement mail aux changements d'état d'un incident ────────────────

def _email_incident_subscribers(db, inc, new_status):
    """Envoie un mail aux abonnés de l'incident lors d'un changement d'état.
    Best-effort : toute erreur est silencieuse (ne doit jamais bloquer la mise
    à jour du statut). Réutilise le canal mail (SMTP) configuré côté serveur."""
    try:
        from app.models import IncidentMailSub, User
        subs = db.query(IncidentMailSub).filter(IncidentMailSub.incident_id == inc.id).all()
        if not subs:
            return
        from plugins.notifications.models import NotifChannel
        from plugins.notifications.backends import BACKENDS, NotifPayload
        from plugins.notifications.dispatcher import _apply_central_config
        import json as _j, asyncio
        ch = (db.query(NotifChannel)
                .filter(NotifChannel.kind == "mail", NotifChannel.enabled == True)  # noqa: E712
                .first())
        if not ch:
            return
        cfg = _apply_central_config("mail", _j.loads(ch.config_json or "{}"))
        backend_cls = BACKENDS.get("mail")
        if not backend_cls:
            return
        backend = backend_cls(cfg)
        if not backend.is_configured():
            return
        # Adresses des abonnés (résolues depuis User.email)
        uids = [s.user_id for s in subs]
        users = db.query(User).filter(User.id.in_(uids),
                                      User.email.isnot(None), User.email != "").all()
        emails = [u.email for u in users]
        if not emails:
            return
        titre = f"[SCRIBE] Incident #{inc.id} → {new_status}"
        corps = (f"L'incident #{inc.id} a changé d'état : {new_status}.\n\n"
                 f"{(inc.fait or '')[:600]}")
        payload = NotifPayload(event_type="incident_status", title=titre, body=corps,
                               urgency=3, context={})
        async def _send_all():
            for addr in emails:
                try:
                    await backend.send(payload, addr)
                except Exception:
                    pass
        asyncio.run(_send_all())
    except Exception:
        pass


class _IncSubResult(BaseModel):
    subscribed: bool


@router.post("/{incident_id}/subscribe")
def subscribe_incident(incident_id: int, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    """Abonne l'utilisateur courant aux mails de changement d'état de l'incident."""
    from app.models import IncidentMailSub
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not inc:
        raise HTTPException(404, "Incident non trouvé")
    existing = (db.query(IncidentMailSub)
                  .filter(IncidentMailSub.incident_id == incident_id,
                          IncidentMailSub.user_id == user.id).first())
    if not existing:
        db.add(IncidentMailSub(incident_id=incident_id, user_id=user.id))
        try:
            db.commit()
        except Exception:
            db.rollback()
    has_email = bool(getattr(user, "email", None))
    return {"subscribed": True, "has_email": has_email}


@router.delete("/{incident_id}/subscribe")
def unsubscribe_incident(incident_id: int, db: Session = Depends(get_db),
                         user=Depends(get_current_user)):
    from app.models import IncidentMailSub
    (db.query(IncidentMailSub)
       .filter(IncidentMailSub.incident_id == incident_id,
               IncidentMailSub.user_id == user.id).delete())
    try:
        db.commit()
    except Exception:
        db.rollback()
    return {"subscribed": False}


@router.get("/my-subscriptions")
def my_incident_subscriptions(db: Session = Depends(get_db),
                              user=Depends(get_current_user)):
    """IDs des incidents auxquels l'utilisateur courant est abonné par mail."""
    from app.models import IncidentMailSub
    rows = (db.query(IncidentMailSub.incident_id)
              .filter(IncidentMailSub.user_id == user.id).all())
    return {"incident_ids": [r[0] for r in rows]}
