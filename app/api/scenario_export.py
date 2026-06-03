"""
app/api/scenario_export.py — SCRIBE v2.3.92 (build v2306)

Endpoint admin : génère et télécharge un scénario JSON à partir d'une
crise passée. L'admin choisit la fenêtre temporelle, les catégories
d'événements à inclure, et l'anonymisation.

Usage :
  POST /api/v1/admin/scenario/export
  {
    "titre": "REX 2026-04-23 ransomware",
    "description": "Crise réelle, pour rejouage annuel",
    "since": "2026-04-23T08:00:00Z",     // optionnel
    "until": "2026-04-23T18:00:00Z",     // optionnel
    "cible_sigle": "DEMO1",
    "anonymize": true,
    "include_incidents": true,
    "include_messages": true,
    "include_transferts": true,
    "type_crise": "CYBER",
    "complexite": "DIFFICILE"
  }

Retourne : {"ok": true, "scenario": {...}, "stimuli_count": N}

Ou POST /api/v1/admin/scenario/export?download=1 → fichier JSON à
télécharger directement.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import require_admin
from app.models import User
from app.scenario_generator import generate_scenario_from_crisis, serialize_scenario

router = APIRouter(prefix="/api/v1/admin/scenario", tags=["admin-scenario"])


class ScenarioExportIn(BaseModel):
    titre: str = Field(..., min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    cible_sigle: str = Field(default="DEMO1", max_length=20)
    anonymize: bool = Field(default=True)
    include_incidents: bool = True
    include_messages: bool = True
    include_transferts: bool = True
    type_crise: str = Field(default="MIXTE", max_length=20)
    complexite: str = Field(default="MOYEN", max_length=20)


@router.post("/export")
def export_scenario(
    body: ScenarioExportIn,
    download: int = Query(default=0, description="Si 1, retourne le JSON en fichier à télécharger"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Génère un scénario JSON à partir de la base de crise actuelle.

    - `download=0` (défaut) : retourne un objet JSON avec métadonnées +
      scénario, pour aperçu dans l'UI.
    - `download=1` : retourne un fichier JSON téléchargeable directement.
    """
    try:
        scenario = generate_scenario_from_crisis(
            db,
            titre=body.titre,
            description=body.description,
            since=body.since,
            until=body.until,
            cible_sigle=body.cible_sigle,
            anonymize=body.anonymize,
            include_incidents=body.include_incidents,
            include_messages=body.include_messages,
            include_transferts=body.include_transferts,
            type_crise=body.type_crise,
            complexite=body.complexite,
        )
    except Exception as e:
        raise HTTPException(500, f"Erreur génération scénario : {e}")

    stimuli_count = len(scenario.get("stimuli", []))

    if download:
        # Télécharger directement en fichier
        json_bytes = serialize_scenario(scenario).encode("utf-8")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in body.titre)[:60]
        filename = f"scenario_{safe_name}.json"
        return Response(
            content=json_bytes,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    # Mode aperçu
    return {
        "ok": True,
        "stimuli_count": stimuli_count,
        "anonymized": scenario["meta"].get("anonymized", False),
        "scenario": scenario,
    }


@router.get("/crisis-preview")
def crisis_preview(
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Aperçu rapide du nombre d'événements disponibles pour génération.

    Permet à l'admin de calibrer sa fenêtre temporelle avant l'export.
    """
    from app.models import SitrepEntry, MessageInterne, TransfertPatient, Decision

    q_inc = db.query(SitrepEntry)
    q_msg = db.query(MessageInterne)
    q_tr  = db.query(TransfertPatient)
    q_dec = db.query(Decision)

    if since:
        q_inc = q_inc.filter(SitrepEntry.timestamp >= since)
        q_msg = q_msg.filter(MessageInterne.created_at >= since)
        q_tr  = q_tr.filter(TransfertPatient.horodatage_creation >= since)
        q_dec = q_dec.filter(Decision.timestamp >= since)
    if until:
        q_inc = q_inc.filter(SitrepEntry.timestamp <= until)
        q_msg = q_msg.filter(MessageInterne.created_at <= until)
        q_tr  = q_tr.filter(TransfertPatient.horodatage_creation <= until)
        q_dec = q_dec.filter(Decision.timestamp <= until)

    # Premier et dernier événement (pour T+0 prévu)
    first_inc = q_inc.order_by(SitrepEntry.timestamp.asc()).first()
    last_inc  = q_inc.order_by(SitrepEntry.timestamp.desc()).first()

    return {
        "ok": True,
        "counts": {
            "incidents":  q_inc.count(),
            "messages":   q_msg.count(),
            "transferts": q_tr.count(),
            "decisions":  q_dec.count(),
        },
        "first_event": first_inc.timestamp.isoformat() if first_inc and first_inc.timestamp else None,
        "last_event":  last_inc.timestamp.isoformat()  if last_inc  and last_inc.timestamp  else None,
    }
