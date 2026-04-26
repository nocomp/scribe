"""
api/rex.py — Tableau de bord REX (Retour d'Expérience) v5
Métriques agrégées : MTTD, MTTR, taux de jalons, récurrence par pôle/type.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from datetime import datetime, timezone
from typing import Optional
import json

from app.database import get_db
from app.models import SitrepEntry, Decision, Presence

router = APIRouter()


def _minutes_between(a, b) -> Optional[float]:
    """Retourne la durée en minutes entre deux datetime (None si impossible)."""
    if not a or not b:
        return None
    try:
        ta = a.replace(tzinfo=timezone.utc) if a.tzinfo is None else a
        tb = b.replace(tzinfo=timezone.utc) if b.tzinfo is None else b
        return round((tb - ta).total_seconds() / 60, 1)
    except Exception:
        return None


@router.get("/dashboard")
def get_rex_dashboard(db: Session = Depends(get_db)):
    """
    Retourne toutes les métriques REX agrégées pour le tableau de bord.
    """
    all_inc = db.query(SitrepEntry).all()
    resolved = [i for i in all_inc if i.status == "RÉSOLU" and i.resolved_at]
    open_inc  = [i for i in all_inc if i.status != "RÉSOLU"]

    # ── MÉTRIQUES GLOBALES ────────────────────────────────
    total       = len(all_inc)
    nb_resolved = len(resolved)
    nb_open     = len(open_inc)

    # MTTR (Mean Time To Resolve) en minutes
    mttrs = []
    for i in resolved:
        m = _minutes_between(i.timestamp, i.resolved_at)
        if m is not None and m >= 0:
            mttrs.append(m)
    mttr_avg = round(sum(mttrs) / len(mttrs), 0) if mttrs else None

    # Taux de complétion jalons (incidents avec jalons)
    jalon_rates = []
    for i in all_inc:
        if i.jalons:
            try:
                js = json.loads(i.jalons)
                if js:
                    done = sum(1 for j in js if j.get("done"))
                    jalon_rates.append(round(done / len(js) * 100))
            except Exception:
                pass
    jalon_rate_avg = round(sum(jalon_rates) / len(jalon_rates)) if jalon_rates else None

    # ── PAR TYPE DE CRISE ─────────────────────────────────
    by_type = {}
    for t in ["CYBER", "SANITAIRE", "MIXTE"]:
        incs_t = [i for i in all_inc if i.type_crise == t]
        res_t  = [i for i in incs_t if i.status == "RÉSOLU" and i.resolved_at]
        mttrs_t = []
        for i in res_t:
            m = _minutes_between(i.timestamp, i.resolved_at)
            if m is not None and m >= 0:
                mttrs_t.append(m)
        by_type[t] = {
            "total":    len(incs_t),
            "resolved": len(res_t),
            "mttr_avg": round(sum(mttrs_t) / len(mttrs_t), 0) if mttrs_t else None,
        }

    # ── PAR URGENCE ───────────────────────────────────────
    by_urgency = {}
    for u in [1, 2, 3, 4]:
        incs_u = [i for i in all_inc if i.urgency == u]
        res_u  = [i for i in incs_u if i.status == "RÉSOLU" and i.resolved_at]
        by_urgency[str(u)] = {
            "total":    len(incs_u),
            "resolved": len(res_u),
        }

    # ── PAR SITE ──────────────────────────────────────────
    sites = {}
    for i in all_inc:
        s = i.site_id or "Inconnu"
        sites.setdefault(s, {"total": 0, "resolved": 0})
        sites[s]["total"] += 1
        if i.status == "RÉSOLU":
            sites[s]["resolved"] += 1

    # ── RÉCURRENCE PAR DIRECTEUR ──────────────────────────
    directors = {}
    for i in all_inc:
        d = i.directeur_crise or "Non assigné"
        directors.setdefault(d, 0)
        directors[d] += 1
    directors_sorted = sorted(directors.items(), key=lambda x: -x[1])[:10]

    # ── CHRONOLOGIE MENSUELLE ─────────────────────────────
    monthly = {}
    for i in all_inc:
        if i.timestamp:
            key = i.timestamp.strftime("%Y-%m")
            monthly.setdefault(key, {"total": 0, "resolved": 0, "cyber": 0, "sanitaire": 0})
            monthly[key]["total"] += 1
            if i.status == "RÉSOLU":
                monthly[key]["resolved"] += 1
            if i.type_crise == "CYBER":
                monthly[key]["cyber"] += 1
            elif i.type_crise == "SANITAIRE":
                monthly[key]["sanitaire"] += 1
    monthly_sorted = [{"month": k, **v} for k, v in sorted(monthly.items())]

    # ── TOP INCIDENTS LES PLUS LONGS À RÉSOUDRE ───────────
    worst = sorted(
        [(i, _minutes_between(i.timestamp, i.resolved_at)) for i in resolved],
        key=lambda x: -(x[1] or 0)
    )[:5]
    top_slow = [{
        "id":       i.id,
        "fait":     i.fait[:80],
        "type":     i.type_crise,
        "urgency":  i.urgency,
        "site":     i.site_id,
        "mttr_min": m,
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
    } for i, m in worst if m is not None]

    # ── ACTIVITÉ CELLULE ──────────────────────────────────
    nb_decisions = db.query(Decision).count()
    nb_presences = db.query(Presence).count()

    return {
        "summary": {
            "total":        total,
            "resolved":     nb_resolved,
            "open":         nb_open,
            "resolution_rate": round(nb_resolved / total * 100) if total else 0,
            "mttr_avg_min": mttr_avg,
            "jalon_rate_avg": jalon_rate_avg,
            "nb_decisions": nb_decisions,
        },
        "by_type":      by_type,
        "by_urgency":   by_urgency,
        "by_site":      sites,
        "directors":    directors_sorted,
        "monthly":      monthly_sorted,
        "top_slow":     top_slow,
    }


@router.get("/incident/{incident_id}/fiche")
def get_fiche_incident(incident_id: int, db: Session = Depends(get_db)):
    """Retourne toutes les données d'un incident pour la fiche de clôture."""
    inc = db.query(SitrepEntry).filter(SitrepEntry.id == incident_id).first()
    if not inc:
        from fastapi import HTTPException
        raise HTTPException(404, "Incident non trouvé")

    jalons = []
    if inc.jalons:
        try:
            jalons = json.loads(inc.jalons)
        except Exception:
            pass

    mttr = _minutes_between(inc.timestamp, inc.resolved_at)

    return {
        "id":                   inc.id,
        "timestamp":            inc.timestamp.isoformat() if inc.timestamp else None,
        "resolved_at":          inc.resolved_at.isoformat() if inc.resolved_at else None,
        "mttr_minutes":         mttr,
        "declarant_nom":        inc.declarant_nom,
        "directeur_crise":      inc.directeur_crise,
        "site_id":              inc.site_id,
        "unite_fonctionnelle":  inc.unite_fonctionnelle,
        "type_crise":           inc.type_crise,
        "urgency":              inc.urgency,
        "fait":                 inc.fait,
        "analyse":              inc.analyse,
        "moyens_engages":       inc.moyens_engages,
        "actions_remediation":  inc.actions_remediation,
        "intervenant_nom":      inc.intervenant_nom,
        "intervenant_contact":  inc.intervenant_contact,
        "status":               inc.status,
        "completion_percent":   inc.completion_percent,
        "jalons":               jalons,
        "albert_avis":          inc.albert_avis,
    }
