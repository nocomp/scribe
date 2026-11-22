"""
api/albert.py — Endpoints IA pour SCRIBE (fournisseur configurable via config.xml)

Le fournisseur effectif est défini dans config.xml <ia> ou via variables d'environnement.
Ce fichier contient uniquement les prompts et la logique métier.
L'appel réseau est délégué à app/api/ai_router.py.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.ai_router import call_ai, get_ai_config, require_ia_configured

router = APIRouter()


# ── Schémas ──────────────────────────────────────────────

class AlbertRequest(BaseModel):
    fait: str
    analyse: str
    type_crise: str = "CYBER"


class IncidentResume(BaseModel):
    fait: str
    analyse: Optional[str] = ""
    status: str
    urgency: int
    type_crise: str
    site_id: str


class SituationGlobaleRequest(BaseModel):
    incidents: List[IncidentResume]
    decisions: Optional[List[str]] = []
    contexte: Optional[str] = ""
    poles_impactes: Optional[str] = ""




# ── Contexte mobilisation pour l'aide à la décision ──────────────────────────
# RGPD : on n'expose JAMAIS de nominatif (nom/téléphone/email) à l'IA. Seuls
# remontent des AGRÉGATS par compétence (fonction) et par délai d'arrivée (ETA).
def _mobilisation_context(db) -> str:
    try:
        from app.models import AlerteMobilisation, AlerteCible
    except Exception:
        return ""
    try:
        alerts = (db.query(AlerteMobilisation)
                    .order_by(AlerteMobilisation.id.desc()).limit(10).all())
        alerts = [a for a in alerts if not getattr(a, "archived", 0)]
    except Exception:
        return ""
    if not alerts:
        return ""
    _eta_lbl = {"15": "moins de 15 min", "30": "environ 30 min",
                "60": "environ 1 h", "indispo": "indisponible"}
    blocs = []
    for a in alerts:
        cibles = db.query(AlerteCible).filter(AlerteCible.alerte_id == a.id).all()
        total = len(cibles)
        rep = sum(1 for c in cibles if c.statut == "repondu")
        eta_counts = {"15": 0, "30": 0, "60": 0, "indispo": 0}
        comp_soon = {}   # compétences arrivant sous ~30 min
        for c in cibles:
            if c.statut == "repondu" and c.eta_choice in eta_counts:
                eta_counts[c.eta_choice] += 1
                if c.eta_choice in ("15", "30"):
                    f = (c.fonction or "Compétence non précisée").strip()
                    comp_soon[f] = comp_soon.get(f, 0) + 1
        taux = round(rep / total * 100) if total else 0
        ligne = (f'- Campagne "{a.titre}" : {total} sollicité(s), {rep} réponse(s) ({taux}%). '
                 f'Arrivées déclarées — <15 min: {eta_counts["15"]}, ~30 min: {eta_counts["30"]}, '
                 f'~1 h: {eta_counts["60"]}, indisponible: {eta_counts["indispo"]}.')
        if comp_soon:
            comp = ", ".join(f"{k} x{v}" for k, v in sorted(comp_soon.items(), key=lambda x: -x[1]))
            ligne += f" Compétences arrivant sous 30 min : {comp}."
        else:
            ligne += " Aucune compétence confirmée sous 30 min pour l'instant."
        en_attente = sum(1 for c in cibles if c.statut == "attente")
        echecs = sum(1 for c in cibles if getattr(c, "livraison", "") == "echec")
        if getattr(a, "vague_courante", 0):
            ligne += f" Escalade : vague {a.vague_courante} en cours"
            if en_attente:
                next_w = min((c.vague for c in cibles if c.statut == "attente"), default=None)
                ligne += f" ; {en_attente} destinataire(s) en attente (vague suivante : {next_w})"
            ligne += "."
        if echecs:
            ligne += f" {echecs} echec(s) d'envoi (a relancer)."
        blocs.append(ligne)
    return ("MOBILISATION EN COURS (chaîne d'alerte / rappel du personnel) — "
            "données agrégées par compétence et délai, sans nominatif :\n" + "\n".join(blocs))

# ── Prompts système ──────────────────────────────────────

SYSTEM_CYBER = """Tu es un expert en gestion de crise cyber pour les hôpitaux publics français.
Tu connais les référentiels ANSSI, NIS2, CERT Santé et les plans de réponse hospitaliers.
Sois concis, opérationnel et PROPORTIONNEL à la gravité réelle. Réponds en français."""

SYSTEM_SANITAIRE = """Tu es un expert en gestion de crise sanitaire hospitalière.
Tu connais le Plan Blanc, ORSAN, et les procédures de l'ARS.
Sois concis, opérationnel et PROPORTIONNEL à la gravité réelle. Réponds en français."""

SYSTEM_GLOBAL = """Tu es conseiller en gestion de crise pour un établissement de santé hospitalier.
Ton rôle : fournir une aide à la décision PROPORTIONNELLE et CALIBRÉE à la situation réelle.

RÈGLES IMPÉRATIVES :
- Si aucune cellule de crise n'est activée, la situation est au maximum en VEILLE ou ALERTE.
- Adapte tes recommandations au niveau d'urgence déclaré (1=info, 2=modéré, 3=grave, 4=critique).
- Un incident isolé de faible urgence = recommandations de surveillance, pas de crise.
- Ne cite les obligations NIS2/ANSSI (notification 24h) que si l'incident est CYBER et urgence >= 2.
- Sois synthétique : 3-4 phrases max par section. Évite le catastrophisme inutile.

AIDE À LA DÉCISION — MOBILISATION :
- Si une « MOBILISATION EN COURS » est fournie, CROISE les compétences qui arrivent (et leur délai) avec les incidents ouverts.
- Tu peux RECOMMANDER d'attendre un renfort interne plutôt que d'engager un prestataire externe quand une compétence pertinente arrive sous peu (ex. « 2 techniciens < 30 min : attendre leur constat avant d'engager un prestataire »).
- Tu peux PROPOSER d'organiser un rappel d'un type de personnel quand un incident le justifie (ex. perte d'Active Directory un week-end → proposer un rappel de techniciens DSI).
- Sépare toujours le FAIT (ce que disent les retours) de la RECOMMANDATION. Une réponse « j'arrive » est une déclaration, pas une garantie ; une compétence présente ne garantit pas la résolution.
- Si une campagne est EN ESCALADE et que la couverture reste insuffisante alors que des destinataires d'une vague suivante sont en attente, tu peux PROPOSER de lancer la vague suivante (priorité supérieure) — la cellule confirme.
- Tu PROPOSES et tu OBSERVES, tu ne déclenches JAMAIS d'alerte ni d'action toi-même : la cellule décide et valide.
Réponds en français."""


# ── Utilitaires ──────────────────────────────────────────

def _extract_niveau(text: str) -> str:
    t = text.upper()
    if "CRITIQUE" in t: return "CRITIQUE"
    if "CRISE"    in t: return "CRISE"
    if "ALERTE"   in t: return "ALERTE"
    if "VEILLE"   in t: return "VEILLE"
    return "ANALYSE"


# ── Endpoints ────────────────────────────────────────────

@router.get("/config")
async def get_ia_config_info():
    """Retourne le fournisseur IA actif (affiché dans l'interface)."""
    cfg = get_ai_config()
    return {
        "provider":     cfg.provider,
        "model":        cfg.model,
        "display_name": cfg.display_name,
        "is_local":     cfg.is_local,
    }


@router.post("/analyser")
async def analyser_incident(req: AlbertRequest):
    """Analyse un incident individuel et retourne un avis structuré."""
    err = require_ia_configured()
    if err:
        raise HTTPException(status_code=400, detail=err)
    system = SYSTEM_CYBER if req.type_crise == "CYBER" else SYSTEM_SANITAIRE
    prompt = (
        f"FAIT DÉCLARÉ : {req.fait}\n"
        f"ANALYSE D'IMPACT : {req.analyse or 'Non renseignée'}\n\n"
        "Donne EXACTEMENT dans cet ordre :\n"
        "NIVEAU: [VEILLE|ALERTE|CRISE|CRITIQUE]\n"
        "ACTIONS:\n1. ...\n2. ...\n3. ...\n"
        "NOTIFIER: [liste des organismes]\n"
        "RISQUE: [Faible|Moyen|Élevé] — [justification courte]"
    )
    try:
        text, source = await call_ai(system, prompt)
        return {
            "recommandation": text,
            "niveau_alerte":  _extract_niveau(text),
            "source":         source,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"IA indisponible : {str(e)}")


@router.post("/situation-globale")
async def analyser_situation_globale(req: SituationGlobaleRequest, db: Session = Depends(get_db)):
    """Analyse globale : tous les incidents ouverts + décisions prises."""
    if not req.incidents:
        return {"analyse": "Aucun incident ouvert.", "niveau_global": "VEILLE", "source": "—"}

    err = require_ia_configured()
    if err:
        raise HTTPException(status_code=400, detail=err)

    incidents_txt = "\n".join([
        f"- [{i.type_crise}] Urgence {i.urgency}/4 | {i.site_id} | {i.status} : {i.fait}"
        + (f" → Impact : {i.analyse}" if i.analyse else "")
        for i in req.incidents
    ])
    decisions_txt = (
        "\n".join([f"- {d}" for d in req.decisions])
        if req.decisions else "Aucune décision actée."
    )
    max_urgency  = max((i.urgency for i in req.incidents), default=1)
    nb_incidents = len(req.incidents)
    severite_note = (
        "SITUATION CRITIQUE — plusieurs incidents graves" if max_urgency >= 3 and nb_incidents >= 2
        else "INCIDENT GRAVE — surveillance renforcée requise" if max_urgency >= 3
        else "INCIDENT MODÉRÉ — suivi en cours" if max_urgency >= 2
        else "INCIDENT MINEUR — veille standard"
    )
    contexte = req.contexte or "Aucune cellule de crise activée. Situation de veille."
    poles    = req.poles_impactes or "Non déterminé"
    _mob = _mobilisation_context(db)
    _mob_block = (_mob + "\n\n") if _mob else ""

    prompt = (
        f"CONTEXTE ORGANISATIONNEL : {contexte}\n"
        f"ÉVALUATION AUTOMATIQUE : {severite_note} (urgence max {max_urgency}/4, {nb_incidents} incident(s))\n"
        f"PÔLES SOINS IMPACTÉS : {poles}\n\n"
        f"INCIDENTS OUVERTS :\n{incidents_txt}\n\n"
        f"DÉCISIONS DÉJÀ PRISES :\n{decisions_txt}\n\n"
        f"{_mob_block}"
        "Produis UNIQUEMENT ces 4 sections, de façon PROPORTIONNELLE à la situation :\n"
        "1. SYNTHÈSE (2-3 phrases)\n"
        "2. NIVEAU GLOBAL : [VEILLE|ALERTE|CRISE|CRITIQUE] — justification en 1 phrase\n"
        "3. ACTIONS PRIORITAIRES (2-3 actions max, adaptées au niveau)\n"
        "4. POINTS DE VIGILANCE (risques d'escalade éventuels, ou RAS si situation stable)"
    )
    try:
        text, source = await call_ai(SYSTEM_GLOBAL, prompt, max_tokens=900)
        return {
            "analyse":       text,
            "niveau_global": _extract_niveau(text),
            "source":        source,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"IA indisponible : {str(e)}")


@router.get("/models")
async def list_models():
    """Liste les modèles disponibles (diagnostic, Albert uniquement)."""
    import httpx
    cfg = get_ai_config()
    if cfg.provider != "albert":
        return {"info": f"Liste des modèles non disponible pour {cfg.provider}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://albert.api.etalab.gouv.fr/v1/models",
                headers={"Authorization": f"Bearer {cfg.api_key}"}
            )
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

# ── Endpoint ANALYSE DE CRISE (debriefing) ───────────────────────────────

class AnalyseCriseRequest(BaseModel):
    question: str
    main_courante: Optional[str] = None   # contexte main courante ou capacitaire
    type_analyse: Optional[str] = "crise" # "crise" | "capacitaire"
    mode: Optional[str] = "analyse_crise"

@router.post("/analyse-crise")
async def analyse_crise(req: AnalyseCriseRequest, db: Session = Depends(get_db)):
    """Répond à une question libre sur une main courante ou situation capacitaire."""
    err = require_ia_configured()
    if err:
        raise HTTPException(status_code=400, detail=err)
    if req.type_analyse == "capacitaire":
        system = (
            "Tu es un expert en gestion capacitaire hospitalière. "
            "On te fournit l'état capacitaire actuel d'un établissement (lits disponibles, "
            "tensions RH, statut matériel) et une question de la cellule de crise. "
            "Réponds de façon concise, opérationnelle et priorisée. "
            "Identifie les risques immédiats, propose des actions concrètes. "
            "Réponds toujours en français."
        )
    else:
        system = (
            "Tu es un expert en gestion de crise hospitalière et en analyse post-incident. "
            "On te fournit une main courante chronologique de crise et une question. "
            "Réponds de façon concise, structurée et opérationnelle. "
            "Identifie les patterns, délais critiques, décisions manquées ou bonnes pratiques. "
            "Réponds toujours en français sauf si la question est dans une autre langue."
        )
    # Injecter le contexte (main courante + mobilisation agrégée) si disponible
    _mob = _mobilisation_context(db)
    _ctx_parts = []
    if req.main_courante:
        _ctx_parts.append(req.main_courante)
    if _mob:
        _ctx_parts.append(_mob)
    full_prompt = req.question
    if _ctx_parts:
        full_prompt = "CONTEXTE:\n" + "\n\n".join(_ctx_parts) + "\n\nQUESTION: " + req.question
    try:
        from app.api.ai_router import call_ai
        text, source = await call_ai(system=system, prompt=full_prompt, max_tokens=700)
        return {"analyse": text, "source": source}
    except Exception as e:
        return {"analyse": f"Erreur IA : {str(e)}"}


class AskRequest(BaseModel):
    question: str
    contexte: str = ""

@router.post("/ask")
async def ask_albert(req: AskRequest, db: Session = Depends(get_db)):
    """Question libre à Albert AI — avec contexte optionnel pour les questions de suivi."""
    err = require_ia_configured()
    if err:
        raise HTTPException(status_code=400, detail=err)
    _mob = _mobilisation_context(db)
    _parts = []
    if req.contexte:
        _parts.append("Contexte de l'analyse précédente :\n" + req.contexte[:600])
    if _mob:
        _parts.append(_mob)
    prompt = req.question
    if _parts:
        prompt = "\n\n".join(_parts) + "\n\nQuestion : " + req.question
    try:
        text, source = await call_ai(
            system=("Tu es un expert en gestion de crise hospitalière. Réponds en français, de façon concise et opérationnelle. "
                    "Si un état de mobilisation en cours est fourni, croise les compétences qui arrivent (et leur délai) avec la situation pour aider à la décision ; "
                    "sépare le fait de la recommandation, et tu PROPOSES/OBSERVES sans jamais déclencher d'action toi-même."),
            prompt=prompt,
            max_tokens=600
        )
        return {"reponse": text, "source": source}
    except Exception as e:
        raise HTTPException(500, f"Erreur IA : {e}")
