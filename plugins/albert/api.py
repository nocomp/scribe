"""
api/albert.py — Endpoints IA pour SCRIBE (fournisseur configurable via config.xml)

Le fournisseur effectif est défini dans config.xml <ia> ou via variables d'environnement.
Ce fichier contient uniquement les prompts et la logique métier.
L'appel réseau est délégué à app/api/ai_router.py.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
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
async def analyser_situation_globale(req: SituationGlobaleRequest):
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

    prompt = (
        f"CONTEXTE ORGANISATIONNEL : {contexte}\n"
        f"ÉVALUATION AUTOMATIQUE : {severite_note} (urgence max {max_urgency}/4, {nb_incidents} incident(s))\n"
        f"PÔLES SOINS IMPACTÉS : {poles}\n\n"
        f"INCIDENTS OUVERTS :\n{incidents_txt}\n\n"
        f"DÉCISIONS DÉJÀ PRISES :\n{decisions_txt}\n\n"
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
async def analyse_crise(req: AnalyseCriseRequest):
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
    # Injecter le contexte dans la question si fourni
    full_prompt = req.question
    if req.main_courante:
        full_prompt = f"CONTEXTE:\n{req.main_courante}\n\nQUESTION: {req.question}"
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
async def ask_albert(req: AskRequest):
    """Question libre à Albert AI — avec contexte optionnel pour les questions de suivi."""
    err = require_ia_configured()
    if err:
        raise HTTPException(status_code=400, detail=err)
    prompt = req.question
    if req.contexte:
        prompt = f"Contexte de l'analyse précédente :\n{req.contexte[:600]}\n\nQuestion : {req.question}"
    try:
        text, source = await call_ai(
            system="Tu es un expert en gestion de crise hospitalière. Réponds en français, de façon concise et opérationnelle.",
            prompt=prompt,
            max_tokens=600
        )
        return {"reponse": text, "source": source}
    except Exception as e:
        raise HTTPException(500, f"Erreur IA : {e}")
