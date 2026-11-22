"""
app/api/status_page.py — Page de statut publique SCRIBE

Permet à l'établissement de publier un point de situation officiel
accessible sans authentification aux ES partenaires, prestataires,
hébergeurs, journalistes et à l'ARS.

Routes internes (auth requise) :
  GET  /api/v1/status/current     → état actuel (pour l'onglet COMMUNIQUÉ)
  PUT  /api/v1/status/update      → publier une mise à jour
  POST /api/v1/status/chronologie → ajouter une entrée à la chronologie publique
  DELETE /api/v1/status/chronologie/{id} → supprimer une entrée
  PUT  /api/v1/status/faq/{index} → mettre à jour une réponse FAQ

Routes publiques (sans auth) :
  GET  /status           → page HTML publique (via main.py)
  GET  /api/v1/status/public → JSON public (pour collecteur + intégrations)
"""

import json
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.database import Base, get_db, SessionLocal
from app.api.auth import get_current_user

router = APIRouter()

# ── Modèles SQLAlchemy ─────────────────────────────────────────────────────

class StatusPage(Base):
    """État courant de la page de statut — une ligne par site (site_id=0 = global)."""
    __tablename__ = "status_page"
    id              = Column(Integer, primary_key=True)
    site_id         = Column(Integer, default=0, index=True)  # 0 = global établissement
    site_nom        = Column(String, default="")  # nom du site pour affichage
    niveau_global   = Column(String, default="OPERATIONNEL")
    # "OPERATIONNEL" | "PERTURBE" | "INCIDENT_MAJEUR" | "MAINTENANCE"
    message_public  = Column(Text, default="")
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by      = Column(String, default="")
    # JSON : liste de {id, label, statut} pour services SI
    services_si     = Column(Text, default="[]")
    # JSON : liste de {id, label, statut} pour prise en charge patients
    prise_en_charge = Column(Text, default="[]")
    # JSON : liste de {id, ts, texte, publie_par}
    chronologie     = Column(Text, default="[]")
    # JSON : liste de {question, reponse, visible}
    faq             = Column(Text, default="[]")
    published       = Column(Boolean, default=False)

class StatusPageChronologie(Base):
    """Entrées de chronologie publique."""
    __tablename__ = "status_chronologie"
    id          = Column(Integer, primary_key=True, index=True)
    timestamp   = Column(DateTime(timezone=True), server_default=func.now())
    texte       = Column(Text, nullable=False)
    publie_par  = Column(String, nullable=True)


# ── Valeurs par défaut ─────────────────────────────────────────────────────

DEFAULT_SERVICES_SI = [
    {"id": "messagerie",   "label": "Messagerie interne",         "statut": "OK"},
    {"id": "dpi",          "label": "Logiciels métier / DPI",     "statut": "OK"},
    {"id": "pacs",         "label": "Imagerie (PACS / RIS)",      "statut": "OK"},
    {"id": "telephonie",   "label": "Téléphonie",                 "statut": "OK"},
    {"id": "internet",     "label": "Accès Internet",             "statut": "OK"},
    {"id": "vpn",          "label": "VPN / accès distants",       "statut": "OK"},
    {"id": "applications", "label": "Applications métier",        "statut": "OK"},
]

DEFAULT_PRISE_EN_CHARGE = [
    {"id": "urgences",     "label": "Urgences",                   "statut": "OK"},
    {"id": "blocs",        "label": "Blocs opératoires",          "statut": "OK"},
    {"id": "consultations","label": "Consultations",              "statut": "OK"},
    {"id": "hospitalisations", "label": "Hospitalisations programmées", "statut": "OK"},
    {"id": "imagerie",     "label": "Imagerie patients",          "statut": "OK"},
    {"id": "laboratoire",  "label": "Laboratoire",                "statut": "OK"},
]

DEFAULT_FAQ = [
    {"question": "Peut-on envoyer des données / imagerie à l'établissement ?",
     "reponse": "", "visible": False},
    {"question": "Les blocs opératoires sont-ils ouverts ?",
     "reponse": "", "visible": False},
    {"question": "Les urgences sont-elles opérationnelles ?",
     "reponse": "", "visible": False},
    {"question": "Comment joindre l'équipe informatique ?",
     "reponse": "", "visible": False},
    {"question": "Les accès VPN partenaires sont-ils disponibles ?",
     "reponse": "", "visible": False},
    {"question": "Quel est l'impact sur la prise en charge des patients ?",
     "reponse": "", "visible": False},
]


def _get_or_create(db: Session, site_id: int = 0, site_nom: str = "") -> StatusPage:
    """Retourne la ligne de statut pour un site donné (0=global), la crée si absente."""
    row = db.query(StatusPage).filter_by(site_id=site_id).first()
    if not row:
        # Calculer le prochain id disponible
        max_id = db.query(StatusPage).count()
        row = StatusPage(
            id=max_id + 1,
            site_id=site_id,
            site_nom=site_nom,
            published=True,
            services_si=json.dumps(DEFAULT_SERVICES_SI, ensure_ascii=False),
            prise_en_charge=json.dumps(DEFAULT_PRISE_EN_CHARGE, ensure_ascii=False),
            faq=json.dumps(DEFAULT_FAQ, ensure_ascii=False),
            chronologie="[]",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        # Mettre à jour le nom si fourni
        if site_nom and not row.site_nom:
            row.site_nom = site_nom
            db.commit()
    return row


def _lignes_repondeur_publiques(db) -> list:
    """Lignes du répondeur ACTIVES (libellé + numéro), non-nominatif.

    Défensif : le plugin Répondeur peut être absent ou sa table inexistante.
    Renvoie [] au moindre problème — n'impacte jamais la page de statut.
    """
    try:
        from plugins.repondeur.models import RepondeurLigne
        rows = (db.query(RepondeurLigne)
                .filter_by(actif=True)
                .order_by(RepondeurLigne.ordre, RepondeurLigne.id).all())
        out = []
        for l in rows:
            if not l.numero:
                continue
            try:
                langues = l.langues_list()
            except Exception:
                langues = []
            out.append({"libelle": l.libelle, "numero": l.numero, "langues": langues})
        return out
    except Exception:
        return []


def _global_impact_active(db) -> bool:
    """h96 — Incident à impact transversal actif (non résolu) ?"""
    try:
        from app.models import SitrepEntry
        return db.query(SitrepEntry).filter(
            SitrepEntry.impact_global == True,  # noqa: E712
            SitrepEntry.resolved_at.is_(None),
            SitrepEntry.archived == False,  # noqa: E712
        ).first() is not None
    except Exception:
        return False


def _row_to_dict(row: StatusPage, chrons: list) -> dict:
    return {
        "site_id":         row.site_id,
        "site_nom":        row.site_nom or "",
        "niveau_global":   row.niveau_global,
        "message_public":  row.message_public or "",
        "updated_at":      row.updated_at.isoformat() if row.updated_at else "",
        "updated_by":      row.updated_by or "",
        "services_si":     json.loads(row.services_si or "[]"),
        "prise_en_charge": json.loads(row.prise_en_charge or "[]"),
        "chronologie":     chrons,
        "faq":             json.loads(row.faq or "[]"),
        "published":       row.published,
    }


def _load_etablissement() -> dict:
    """Nom/sigle de l'établissement. config.js d'abord (extraction par
    équilibrage d'accolades, tolérante au format), puis REPLI sur config.xml
    (que l'instance possède toujours) — évite le fallback générique."""
    # 1) config.js
    config_js = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "app", "static", "config.js"
    )
    try:
        raw = open(config_js, encoding="utf-8").read()
        i = raw.find("SCRIBE_CONFIG")
        if i != -1:
            b = raw.find("{", i)
            if b != -1:
                depth, end = 0, -1
                for j in range(b, len(raw)):
                    c = raw[j]
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            end = j + 1
                            break
                if end != -1:
                    cfg = json.loads(raw[b:end])
                    etab = cfg.get("etablissement", {}) or {}
                    if etab.get("nom"):
                        return etab
    except Exception:
        pass
    # 2) Repli config.xml
    try:
        import xml.etree.ElementTree as ET
        path = os.environ.get("SCRIBE_CONFIG_FILE", "config.xml")
        root = ET.parse(path).getroot()
        e = root.find("etablissement")
        if e is not None:
            nom = (e.findtext("nom") or "").strip()
            sigle = (e.findtext("sigle") or "").strip()
            if nom or sigle:
                return {"nom": nom, "sigle": sigle}
    except Exception:
        pass
    return {}


# ── Schémas Pydantic ───────────────────────────────────────────────────────

class StatusUpdateRequest(BaseModel):
    niveau_global:   str
    message_public:  Optional[str] = ""
    services_si:     Optional[list] = None
    prise_en_charge: Optional[list] = None
    faq:             Optional[list] = None
    published:       Optional[bool] = None

class ChronologieEntry(BaseModel):
    texte: str

class FaqUpdate(BaseModel):
    reponse: str
    visible: bool


# ── Routes internes (auth) ─────────────────────────────────────────────────

@router.get("/current")
def get_current(site_id: int = 0, site_nom: str = "", db: Session = Depends(get_db), user=Depends(get_current_user)):
    row    = _get_or_create(db, site_id, site_nom)
    chrons = db.query(StatusPageChronologie).order_by(
        StatusPageChronologie.timestamp.desc()).limit(20).all()
    chrons_list = [
        {"id": c.id, "ts": c.timestamp.isoformat(), "texte": c.texte, "publie_par": c.publie_par or ""}
        for c in chrons
    ]
    data = _row_to_dict(row, chrons_list)
    data["site_id"] = site_id
    data["lignes_repondeur"] = _lignes_repondeur_publiques(db)
    return data


@router.put("/update")
def update_status(req: StatusUpdateRequest, site_id: int = 0, site_nom: str = "", db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    NIVEAUX_VALIDES = {"OPERATIONNEL", "PERTURBE", "INCIDENT_MAJEUR", "MAINTENANCE"}
    if req.niveau_global not in NIVEAUX_VALIDES:
        raise HTTPException(400, f"niveau_global invalide : {req.niveau_global}")

    row = _get_or_create(db, site_id, site_nom)
    row.niveau_global  = req.niveau_global
    row.message_public = req.message_public or ""
    row.updated_by     = getattr(user, "display_name", "") or getattr(user, "username", "")
    if req.services_si     is not None: row.services_si     = json.dumps(req.services_si,     ensure_ascii=False)
    if req.prise_en_charge is not None: row.prise_en_charge = json.dumps(req.prise_en_charge, ensure_ascii=False)
    if req.faq             is not None: row.faq             = json.dumps(req.faq,             ensure_ascii=False)
    if req.published is not None:
        row.published = req.published
    else:
        row.published = True  # Auto-publié par défaut
    db.commit()
    return {"ok": True}


@router.post("/chronologie")
def add_chronologie(entry: ChronologieEntry, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    publie_par = getattr(user, "display_name", "") or getattr(user, "username", "")
    chron = StatusPageChronologie(texte=entry.texte, publie_par=publie_par)
    db.add(chron)
    db.commit()
    return {"ok": True, "id": chron.id}


@router.delete("/chronologie/{entry_id}")
def delete_chronologie(entry_id: int, db: Session = Depends(get_db),
                       user=Depends(get_current_user)):
    c = db.query(StatusPageChronologie).filter_by(id=entry_id).first()
    if not c:
        raise HTTPException(404, "Entrée introuvable")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ── Route publique JSON (sans auth) ───────────────────────────────────────

@router.get("/public")
def get_public(site_id: int = 0, db: Session = Depends(get_db)):
    """Retourne le statut public — accessible sans authentification.
    site_id=0 (défaut) = statut global établissement.
    """
    row = _get_or_create(db, site_id)
    etab = _load_etablissement()
    # Si site_id non trouvé ou non publié, fallback sur global
    if not row.published and site_id != 0:
        row = _get_or_create(db, 0)
    if not row.published:
        return {
            "published": False,
            "message":   "Aucun point de situation publié pour le moment.",
            "etablissement": etab,
        }
    chrons = db.query(StatusPageChronologie).order_by(
        StatusPageChronologie.timestamp.desc()).limit(20).all()
    chrons_list = [
        {"id": c.id, "ts": c.timestamp.isoformat(), "texte": c.texte, "publie_par": c.publie_par or ""}
        for c in chrons
    ]
    data = _row_to_dict(row, chrons_list)
    if data.get("niveau_global") == "OPERATIONNEL" and _global_impact_active(db):
        data["niveau_global"] = "PERTURBE"
        data["impact_global_actif"] = True
    data["etablissement"] = etab
    data["site_id"] = site_id
    data["faq"] = [f for f in data["faq"] if f.get("visible") and f.get("reponse")]
    data["lignes_repondeur"] = _lignes_repondeur_publiques(db)
    return data

@router.get("/all-published")
def get_all_published(db: Session = Depends(get_db)):
    """Retourne tous les statuts publiés (global + sites) pour la fédération."""
    rows = db.query(StatusPage).filter_by(published=True).all()
    chrons = db.query(StatusPageChronologie).order_by(
        StatusPageChronologie.timestamp.desc()).limit(20).all()
    chrons_list = [
        {"id": c.id, "ts": c.timestamp.isoformat(), "texte": c.texte, "publie_par": c.publie_par or ""}
        for c in chrons
    ]
    etab = _load_etablissement()
    result = []
    for row in rows:
        d = _row_to_dict(row, chrons_list)
        d["etablissement"] = etab
        d["site_id"] = row.site_id
        d["faq"] = [f for f in d["faq"] if f.get("visible") and f.get("reponse")]
        result.append(d)
    return result
