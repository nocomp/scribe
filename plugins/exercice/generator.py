"""
plugins/exercice/generator.py — Générateur de scénarios via IA (Albert)
Utilise le routeur IA universel de SCRIBE (app/api/ai_router.py).
"""
import json
import logging
import uuid
from datetime import datetime

logger = logging.getLogger("scribe.exercice.generator")

SYSTEM_EXERCICE = """Tu es un expert en gestion de crise hospitalière et en formation médicale.
Tu conçois des exercices de crise pour des équipes hospitalières françaises.
Tu connais le Plan Blanc, ORSAN, les procédures de l'ARS Auvergne-Rhône-Alpes,
et la coordination inter-hospitalière en GHT (Groupement Hospitalier de Territoire).

Tes scénarios doivent être :
- Réalistes cliniquement et opérationnellement
- Progressifs (montée en charge des stimuli)
- Adaptés au nombre de participants et de sites
- Formateurs : chaque stimulus doit provoquer une décision ou une action attendue
- Conformes aux procédures hospitalières françaises

Tu réponds UNIQUEMENT en JSON valide, sans texte autour, sans balises markdown."""

PROMPT_TEMPLATE = """Génère un scénario d'exercice de crise hospitalière avec les paramètres suivants :

PARAMÈTRES :
- Sujet / contexte clinique : {sujet}
- Nombre de sites participants : {nb_sites}
- Établissements : {sites}
- Durée de l'exercice : {duree_exercice_min} minutes
- Durée simulée de l'incident réel : {duree_reel_min} minutes
- Ratio de compression : {ratio}x (1 min exercice = {ratio} min réelles)
- Niveau de complexité : {complexite}
- Type de crise : {type_crise}
- Langue : {langue}

STRUCTURE JSON ATTENDUE (respecter exactement) :
{{
  "meta": {{
    "id": "exo_{id_auto}",
    "titre": "Titre court et évocateur",
    "description": "Description en 2-3 phrases",
    "sujet": "{sujet}",
    "duree_min": {duree_exercice_min},
    "duree_reel_min": {duree_reel_min},
    "ratio_compression": {ratio},
    "complexite": "{complexite}",
    "type_crise": "{type_crise}",
    "objectifs_pedagogiques": ["objectif 1", "objectif 2", "objectif 3"]
  }},
  "acteurs": [
    {{
      "sigle": "SIGLE_SITE",
      "nom_etablissement": "Nom complet",
      "role": "coordinateur ou participant",
      "port": 8660,
      "joueurs": [
        {{
          "username": "dir_chag_exo",
          "display_name": "Directeur de Crise DEMO1",
          "role_exercice": "Directeur de cellule de crise",
          "responsabilites": ["activation plan blanc", "contact SAMU", "coordination inter-GHT"]
        }}
      ]
    }}
  ],
  "stimuli": [
    {{
      "id": "S01",
      "t_min": 0,
      "cible": "SIGLE_SITE",
      "type": "incident",
      "titre": "Titre court du stimulus",
      "description_animateur": "Ce que voit l'animateur — contexte et objectif pédagogique",
      "payload": {{
        "fait": "Description précise de l'événement pour les joueurs",
        "urgency": 3,
        "type_crise": "SANITAIRE",
        "site_id": "SITE",
        "unite_fonctionnelle": "Maternité",
        "declarant_nom": "Sage-femme coordinatrice",
        "analyse": "",
        "jalons_labels": ["Alerter le chef de service", "Contacter le SAMU", "Activer plan blanc maternité"]
      }},
      "action_attendue": "Description de ce que les joueurs doivent faire",
      "indicateurs_reussite": ["Transfert initié dans les 10 min", "Plan blanc activé"]
    }}
  ],
  "decisions_attendues": [
    {{
      "t_min": 0,
      "contenu": "Activation du plan blanc maternité",
      "responsable": "Directeur de crise",
      "obligatoire": true
    }}
  ],
  "debriefing_guide": {{
    "points_cles": ["Point clé 1", "Point clé 2"],
    "questions_debriefing": ["Question pour le groupe 1", "Question pour le groupe 2"],
    "pieges_frequents": ["Piège 1", "Piège 2"]
  }}
}}

CONTRAINTES IMPORTANTES :
- Les stimuli doivent être espacés progressivement (T+0, T+5, T+10, T+20, etc.)
- Minimum 5 stimuli, maximum 15 pour {duree_exercice_min} minutes
- Les types de stimuli disponibles : incident, message, transfert, chat, capacite, decision
- Pour les exercices multi-sites : alterner les stimuli entre les sites pour forcer la coordination
- Les usernames doivent être en minuscules sans accents ni espaces
- Les ports : DEMO1=8660, DEMO2=8661, DEMO5=8662, DEMO6=8663, DEMO7=8664, DEMO5=8665, DEMO6=8666
- Adapter la complexité : FACILE=alertes simples, MOYEN=coordination inter-services, DIFFICILE=multi-sites, EXPERT=gestion de crise complète avec complications

Génère maintenant le scénario complet en JSON valide."""


async def generate_scenario(
    sujet: str,
    nb_sites: int,
    sites: list,
    duree_exercice_min: int = 60,
    duree_reel_min: int = 240,
    complexite: str = "MOYEN",
    type_crise: str = "SANITAIRE",
    langue: str = "fr",
) -> dict:
    """
    Génère un scénario complet via Albert.
    Retourne le JSON parsé du scénario.
    """
    from app.api.ai_router import call_ai

    ratio = round(duree_reel_min / duree_exercice_min, 1)
    id_auto = datetime.now().strftime("%Y%m%d_%H%M")
    sites_str = ", ".join(sites) if sites else "DEMO1"

    prompt = PROMPT_TEMPLATE.format(
        sujet=sujet,
        nb_sites=nb_sites,
        sites=sites_str,
        duree_exercice_min=duree_exercice_min,
        duree_reel_min=duree_reel_min,
        ratio=ratio,
        complexite=complexite,
        type_crise=type_crise,
        langue=langue,
        id_auto=id_auto,
    )

    logger.info(f"Génération scénario IA — sujet: {sujet}, sites: {sites_str}")

    try:
        response_text = await call_ai(
            system=SYSTEM_EXERCICE,
            user=prompt,
            max_tokens=4000,
        )
        # Nettoyer les backticks markdown si présents
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        scenario = json.loads(clean)
        logger.info(f"Scénario généré : {scenario.get('meta', {}).get('titre', '?')}")
        return {"ok": True, "scenario": scenario}

    except json.JSONDecodeError as e:
        logger.error(f"JSON invalide dans la réponse IA : {e}")
        return {"ok": False, "error": f"Réponse IA non JSON valide : {str(e)}", "raw": response_text[:500]}
    except Exception as e:
        logger.error(f"Erreur génération IA : {e}")
        return {"ok": False, "error": str(e)}


async def generate_bilan(
    session_uid: str,
    scenario: dict,
    injections: list,
    actions: list,
) -> dict:
    """
    Génère le bilan pédagogique post-exercice via IA.
    injections : liste des ExoInjection
    actions : liste des ExoActionLog
    """
    from app.api.ai_router import call_ai

    meta = scenario.get("meta", {})
    decisions_attendues = scenario.get("decisions_attendues", [])
    debriefing = scenario.get("debriefing_guide", {})

    # Construire le résumé des actions pour l'IA
    actions_resume = []
    for a in actions:
        actions_resume.append({
            "t_min": round(a.t_exercice_s / 60, 1),
            "site": a.sigle_site,
            "auteur": a.username,
            "action": a.action_type,
            "detail": a.action_detail,
        })

    injections_resume = []
    for inj in injections:
        injections_resume.append({
            "id": inj.stimulus_id,
            "type": inj.stimulus_type,
            "cible": inj.cible_sigle,
            "t_min_prevu": inj.t_min_prevu,
            "injecte": inj.injected_at.isoformat() if inj.injected_at else None,
            "succes": inj.success,
        })

    system_bilan = """Tu es un formateur expert en gestion de crise hospitalière.
Tu analyses les performances d'une équipe lors d'un exercice de simulation de crise.
Tu es bienveillant mais précis. Tu identifies les forces ET les axes d'amélioration.
Tu fournis des recommandations concrètes et actionnables.
Tu réponds en JSON valide uniquement."""

    prompt_bilan = f"""Analyse les résultats de cet exercice de crise hospitalière.

SCÉNARIO :
- Titre : {meta.get('titre', '?')}
- Type : {meta.get('type_crise', '?')}
- Durée : {meta.get('duree_min', 60)} minutes
- Complexité : {meta.get('complexite', 'MOYEN')}
- Objectifs : {json.dumps(meta.get('objectifs_pedagogiques', []), ensure_ascii=False)}

STIMULI INJECTÉS :
{json.dumps(injections_resume, ensure_ascii=False, indent=2)}

ACTIONS DES JOUEURS :
{json.dumps(actions_resume, ensure_ascii=False, indent=2)}

DÉCISIONS ATTENDUES :
{json.dumps(decisions_attendues, ensure_ascii=False, indent=2)}

GUIDE DÉBRIEFING :
{json.dumps(debriefing, ensure_ascii=False, indent=2)}

Génère un bilan pédagogique complet en JSON :
{{
  "note_globale": 7.5,
  "synthese": "2-3 phrases de synthèse générale",
  "points_forts": ["Point fort 1", "Point fort 2"],
  "axes_amelioration": ["Axe 1", "Axe 2"],
  "analyse_par_site": {{
    "DEMO1": {{
      "note": 8.0,
      "commentaire": "...",
      "points_forts": ["..."],
      "axes_amelioration": ["..."]
    }}
  }},
  "analyse_coordination": "Analyse de la coordination inter-sites",
  "decisions_prises": ["décision 1", "décision 2"],
  "decisions_manquantes": ["décision attendue non prise"],
  "delais_reaction": {{
    "moyen_min": 4.5,
    "commentaire": "Les délais sont..."
  }},
  "recommandations": [
    {{
      "priorite": "HAUTE",
      "domaine": "Coordination",
      "action": "Action recommandée concrète"
    }}
  ],
  "questions_debriefing": ["Question pour la discussion collective"],
  "prochaine_etape": "Suggestion pour le prochain exercice"
}}"""

    try:
        response_text = await call_ai(
            system=system_bilan,
            user=prompt_bilan,
            max_tokens=3000,
        )
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        if clean.endswith("```"):
            clean = clean[:-3]
        bilan = json.loads(clean.strip())
        return {"ok": True, "bilan": bilan}
    except Exception as e:
        logger.error(f"Erreur bilan IA : {e}")
        return {"ok": False, "error": str(e)}
