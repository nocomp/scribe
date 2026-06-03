"""
plugins/tuteur/knowledge_base.py — v3000h18

Charge la base de connaissances réglementaire (data/copilote_knowledge.json)
et fournit les fonctions pour enrichir les alertes du copilote avec :
- coordonnées des autorités (téléphone, mail, URL)
- délais légaux
- modèles de messages pré-remplis avec le contexte courant
- risques en cas de non-déclaration

Stratégie de sécurité :
- Seules les entrées avec verified=true sont exposées à l'utilisateur final
- Les entrées non vérifiées sont chargées mais marquées pour validation manuelle
"""
from __future__ import annotations
import json
import logging
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("scribe.tuteur.kb")

_KB_PATH = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "data" / "copilote_knowledge.json"
)

_CACHED_KB: dict | None = None


def load_knowledge_base() -> dict:
    """Charge la base de connaissances. Cache en mémoire après premier appel.

    Si le fichier est absent ou invalide, retourne un dict vide (graceful)
    pour que le copilote continue de fonctionner sans enrichissement.
    """
    global _CACHED_KB
    if _CACHED_KB is not None:
        return _CACHED_KB
    try:
        if _KB_PATH.exists():
            with open(_KB_PATH, encoding="utf-8") as f:
                _CACHED_KB = json.load(f)
                logger.info(
                    f"Base de connaissances chargée : "
                    f"{len(_CACHED_KB.get('obligations', {}))} obligations"
                )
        else:
            logger.warning(f"Pas de base de connaissances à {_KB_PATH}")
            _CACHED_KB = {"obligations": {}}
    except Exception as e:
        logger.error(f"Erreur chargement KB : {e}")
        _CACHED_KB = {"obligations": {}}
    return _CACHED_KB


def get_obligation(obligation_id: str) -> dict | None:
    """Retourne une obligation par son id, OU None si non vérifiée/inexistante."""
    kb = load_knowledge_base()
    obl = kb.get("obligations", {}).get(obligation_id)
    if obl is None:
        return None
    if not obl.get("verified", False):
        logger.warning(
            f"Obligation '{obligation_id}' demandée mais non vérifiée, ignorée"
        )
        return None
    return obl


def get_obligation_summary(obligation_id: str) -> dict | None:
    """Version compacte de l'obligation pour affichage UI.

    Renvoie : {label, autorite, delai, contacts: [...], risques: [...]}
    Tronqué pour la display, sans le modèle de message complet.
    """
    obl = get_obligation(obligation_id)
    if not obl:
        return None
    contacts_short = []
    for ckey, c in (obl.get("contacts") or {}).items():
        contacts_short.append({
            "label":   c.get("label", ckey),
            "type":    c.get("type", "info"),
            "valeur":  c.get("valeur", ""),
            "note":    c.get("note", ""),
        })
    return {
        "id":          obl["id"],
        "label":       obl["label"],
        "autorite":    obl.get("autorite", ""),
        "delai":       obl.get("delai_legal", ""),
        "fondement":   obl.get("fondement_juridique", ""),
        "contacts":    contacts_short,
        "risques":     obl.get("risque_si_non_declaration") or [],
        "note":        obl.get("note_critique") or "",
        "has_modele":  bool(obl.get("modele_message")),
    }


def render_message_template(
    obligation_id: str,
    context: dict,
) -> dict | None:
    """Génère le message pré-rempli à partir du modèle et du contexte courant.

    Remplace les placeholders {nom_etablissement}, {sigle_etablissement},
    {heure_premier_incident}, etc. par les valeurs du contexte. Les
    placeholders non fournis sont remplacés par "[à compléter]" pour que le
    message reste utilisable même incomplet.

    Retourne {objet, corps} ou None si modèle absent.
    """
    obl = get_obligation(obligation_id)
    if not obl:
        return None
    modele = obl.get("modele_message") or {}
    if not modele:
        return None

    # Construire valeurs par défaut + valeurs de contexte
    now = datetime.now(timezone.utc)
    defaults = {
        "sigle_etablissement":  "[sigle]",
        "nom_etablissement":    "[nom de l'établissement]",
        "finess_etablissement": "[FINESS]",
        "nom_dircrise":         "[nom du directeur de crise]",
        "tel_dircrise":         "[téléphone]",
        "mail_dircrise":        "[mail]",
        "role_declarant":       "Directeur de crise",
        "nom_dpo":              "[DPO de l'établissement]",
        "date":                 now.strftime("%d/%m/%Y"),
        "heure_premier_incident": now.strftime("%H:%M"),
        "heure_decouverte":     now.strftime("%H:%M le %d/%m/%Y"),
        "deadline_72h":         (now + timedelta(hours=72)).strftime(
                                    "%H:%M le %d/%m/%Y"),
        "type_crise":           "[à compléter]",
        "nature_incident":      "[à compléter]",
        "nature_violation":     "[à compléter]",
        "circonstances":        "[à compléter]",
        "categories_donnees":   "[à compléter]",
        "categories_personnes": "Patients pris en charge dans l'établissement",
        "nb_personnes_estime":  "[à compléter]",
        "consequences_possibles": "[à évaluer après analyse technique]",
        "mesures_prises":       "[à compléter]",
        "mesures_envisagees":   "[à compléter]",
        "niveau_tension":       "[à compléter]",
        "nb_critiques":         "[à compléter]",
        "services_impactes":    "[à compléter]",
        "decisions_prises":     "[à compléter]",
        "statut_cellule_crise": "[activée / en cours d'activation]",
        "systemes_impactes":    "[à compléter]",
        "vecteur_suspect_ou_inconnu": "Inconnu — analyse en cours",
        "oui_non_inconnu":      "À déterminer",
        "nb_systemes":          "[à compléter]",
    }
    # Merger avec le contexte fourni (priorité au contexte)
    values = {**defaults, **(context or {})}

    def fill(text: str) -> str:
        result = text
        for key, val in values.items():
            placeholder = "{" + key + "}"
            result = result.replace(placeholder, str(val or "[à compléter]"))
        return result

    return {
        "objet": fill(modele.get("objet", "")),
        "corps": fill(modele.get("corps", "")),
    }
