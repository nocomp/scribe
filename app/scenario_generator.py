"""
app/scenario_generator.py — SCRIBE v2.3.92 (build v2306)

Génère un fichier scénario JSON rejouable à partir du déroulement réel
(ou simulé) d'une crise passée. L'idée est de transformer une main
courante vécue en support d'exercice réutilisable, permettant à l'équipe
(ou à d'autres équipes) de :

  - Rejouer la crise pour valider les mesures de remédiation
  - Former les nouveaux entrants sur un cas concret
  - Partager un retour d'expérience sous forme exécutable
  - Alimenter une bibliothèque nationale de scénarios certifiés

PRINCIPES :

  1. T+0 = horodatage du premier événement considéré, ou borne fournie
     par l'utilisateur.
  2. Chaque incident, message externe entrant, et transfert devient un
     stimulus avec son délai relatif en minutes.
  3. Les décisions prises par l'équipe ne sont PAS des stimuli (ce sont
     des réponses). Elles sont conservées dans un bloc meta
     `actions_observees` pour servir de référence d'évaluation.
  4. Anonymisation optionnelle : noms propres, numéros de dossier,
     identifiants, remplacés par des placeholders.
  5. Le scénario généré est immédiatement compatible avec le collecteur
     d'exercice — aucun post-traitement manuel nécessaire.

SÉCURITÉ :
  - Export réservé admin (géré dans la route API qui appelle ce module)
  - Anonymisation par défaut pour éviter la diffusion accidentelle de
    données identifiantes quand le scénario est partagé
"""
from __future__ import annotations

import re
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import (
    SitrepEntry,
    Decision,
    MessageInterne,
    TransfertPatient,
)

# ─── Anonymisation ───────────────────────────────────────────────────────

# Motifs courants à masquer lors de l'anonymisation "de base". On reste
# volontairement conservateur (faux positifs préférables aux vrais noms
# qui passent). L'opérateur humain doit relire avant publication.
_RE_PHONE = re.compile(r"\b0[1-9](?:[\s.-]?\d{2}){4}\b")
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_IPAM_HOSP = re.compile(r"\bIPP[\s:\-]*\d{4,}\b", re.IGNORECASE)
_RE_NIR = re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b")
# Prénoms + NOM en majuscules (heuristique imparfaite mais utile)
_RE_NOM_PRENOM = re.compile(
    r"\b(?:Dr|Dre|Docteur|Pr|Prof|M\.|Mme|Mlle)\.?\s+[A-ZÉÈÊÀÂÎÏÔÖÛÜÇ][\w'-]+(?:\s+[A-ZÉÈÊÀÂÎÏÔÖÛÜÇ]{2,})?",
)


def _anonymize(text: str) -> str:
    """Masque les motifs sensibles les plus courants dans un texte.
    Conservatrice plutôt qu'exhaustive — l'humain doit relire.
    """
    if not text:
        return text
    text = _RE_NIR.sub("[NIR-MASQUÉ]", text)
    text = _RE_EMAIL.sub("[email-masqué]", text)
    text = _RE_PHONE.sub("[tél-masqué]", text)
    text = _RE_IPAM_HOSP.sub("[IPP-masqué]", text)
    text = _RE_NOM_PRENOM.sub("[Personnel masqué]", text)
    return text


def _text(value: Any, anonymize: bool) -> str:
    s = (value or "") if value is not None else ""
    s = str(s)
    return _anonymize(s) if anonymize else s


# ─── Conversion d'événements vers stimuli ────────────────────────────────

def _incident_to_stimulus(
    inc: SitrepEntry, stimulus_id: str, t_min: int, cible: str, anonymize: bool
) -> Dict[str, Any]:
    return {
        "id": stimulus_id,
        "t_min": t_min,
        "type": "incident",
        "cible": cible,
        "titre": _text(inc.fait, anonymize)[:80] or f"Incident {inc.id}",
        "description_animateur": (
            f"Incident extrait d'une crise passée (SitrepEntry #{inc.id})."
        ),
        "action_attendue": _text(inc.actions_remediation, anonymize) or
                           "Voir le déroulé original de la crise",
        "payload": {
            "fait":                _text(inc.fait, anonymize),
            "analyse":             _text(inc.analyse, anonymize),
            "urgency":             inc.urgency or 2,
            "type_crise":          inc.type_crise or "CYBER",
            "impact_fonctionnel":  bool(inc.impact_fonctionnel),
            "unite_fonctionnelle": inc.unite_fonctionnelle or "",
        },
    }


def _message_to_stimulus(
    msg: MessageInterne, stimulus_id: str, t_min: int, cible: str, anonymize: bool
) -> Dict[str, Any]:
    # Les messages qui comptent pour un scénario sont ceux qui viennent
    # d'acteurs externes (ARS, CERT, SAMU...). On détecte via expediteur_nom
    # quand il contient un tag externe (heuristique). Tolérance sur les
    # colonnes non universellement présentes : getattr avec défaut.
    expediteur = getattr(msg, "expediteur_nom", None) or getattr(msg, "ght_source", None) or ""
    sujet   = getattr(msg, "sujet", "") or ""
    contenu = getattr(msg, "contenu", "") or ""
    return {
        "id": stimulus_id,
        "t_min": t_min,
        "type": "message",
        "cible": cible,
        "titre": _text(sujet, anonymize)[:80] or "Message entrant",
        "description_animateur": (
            f"Message extrait de la messagerie (MessageInterne #{msg.id})."
        ),
        "action_attendue": "Accuser réception et traiter selon les procédures",
        "payload": {
            "expediteur": _text(expediteur, anonymize),
            "sujet":      _text(sujet, anonymize),
            "contenu":    _text(contenu, anonymize),
        },
    }


def _transfert_to_stimulus(
    tr: TransfertPatient, stimulus_id: str, t_min: int, cible: str, anonymize: bool
) -> Dict[str, Any]:
    origine = getattr(tr, "etablissement_origine", "") or "?"
    dest    = getattr(tr, "etablissement_destination", "") or "?"
    # Le motif peut s'appeler "motif" ou "commentaire" selon les versions
    motif   = (getattr(tr, "motif", None) or
               getattr(tr, "commentaire", None) or "")
    statut  = getattr(tr, "statut", "") or ""
    uo      = getattr(tr, "unite_origine", "") or ""
    ud      = getattr(tr, "unite_destination", "") or ""
    return {
        "id": stimulus_id,
        "t_min": t_min,
        "type": "transfert",
        "cible": cible,
        "titre": f"Transfert {origine} → {dest}",
        "description_animateur": (
            f"Transfert extrait de la base (TransfertPatient #{tr.id})."
        ),
        "action_attendue": "Organiser l'accueil ou la sortie selon le sens du transfert",
        "payload": {
            "etablissement_origine":     _text(origine, anonymize),
            "etablissement_destination": _text(dest, anonymize),
            "unite_origine":             _text(uo, anonymize),
            "unite_destination":         _text(ud, anonymize),
            "motif":                     _text(motif, anonymize),
            "statut":                    statut,
        },
    }


# ─── Génération principale ───────────────────────────────────────────────

def generate_scenario_from_crisis(
    db: Session,
    *,
    titre: str,
    description: str = "",
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    cible_sigle: str = "CHV",
    anonymize: bool = True,
    include_incidents: bool = True,
    include_messages: bool = True,
    include_transferts: bool = True,
    type_crise: str = "MIXTE",
    complexite: str = "MOYEN",
) -> Dict[str, Any]:
    """Construit un dictionnaire de scénario prêt à être exporté en JSON.

    Args:
        db: session SQLAlchemy
        titre: titre du scénario généré
        description: description libre (ce qu'on a voulu capturer)
        since: borne basse ; si None, prend le premier événement trouvé
        until: borne haute ; si None, pas de limite supérieure
        cible_sigle: SIGLE de l'établissement cible (par défaut CHV)
        anonymize: applique l'anonymisation aux textes
        include_*: filtres sur les catégories d'événements
        type_crise, complexite: metadata pédagogique
    """

    # 1) Collecte des événements dans la fenêtre temporelle
    events: List[Tuple[datetime, str, Any]] = []

    if include_incidents:
        q = db.query(SitrepEntry).order_by(SitrepEntry.timestamp.asc())
        if since:
            q = q.filter(SitrepEntry.timestamp >= since)
        if until:
            q = q.filter(SitrepEntry.timestamp <= until)
        for inc in q.all():
            if inc.timestamp:
                events.append((inc.timestamp, "incident", inc))

    if include_messages:
        q = db.query(MessageInterne).order_by(MessageInterne.created_at.asc())
        if since:
            q = q.filter(MessageInterne.created_at >= since)
        if until:
            q = q.filter(MessageInterne.created_at <= until)
        for msg in q.all():
            ts = getattr(msg, "created_at", None) or getattr(msg, "timestamp", None)
            if ts:
                events.append((ts, "message", msg))

    if include_transferts:
        q = db.query(TransfertPatient).order_by(
            TransfertPatient.horodatage_creation.asc()
        )
        if since:
            q = q.filter(TransfertPatient.horodatage_creation >= since)
        if until:
            q = q.filter(TransfertPatient.horodatage_creation <= until)
        for tr in q.all():
            if tr.horodatage_creation:
                events.append((tr.horodatage_creation, "transfert", tr))

    # 2) Tri chronologique global
    events.sort(key=lambda e: e[0])

    if not events:
        return {
            "meta": {
                "id": f"generated_{int(datetime.now(timezone.utc).timestamp())}",
                "titre": titre,
                "description": description + "\n\n(Aucun événement trouvé dans la fenêtre sélectionnée.)",
                "nb_stimuli": 0,
                "generated_from_crisis": True,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "acteurs": [],
            "stimuli": [],
        }

    # 3) T+0 = timestamp du premier événement
    t0 = events[0][0]

    # 4) Construction des stimuli
    stimuli: List[Dict[str, Any]] = []
    idx = 1
    for ts, kind, obj in events:
        delta = ts - t0
        t_min = max(0, int(delta.total_seconds() // 60))
        sid = f"S{idx:02d}"
        if kind == "incident":
            stimuli.append(_incident_to_stimulus(obj, sid, t_min, cible_sigle, anonymize))
        elif kind == "message":
            stimuli.append(_message_to_stimulus(obj, sid, t_min, cible_sigle, anonymize))
        elif kind == "transfert":
            stimuli.append(_transfert_to_stimulus(obj, sid, t_min, cible_sigle, anonymize))
        idx += 1

    # 5) Décisions observées (hors stimuli, pour référence d'évaluation)
    decisions_obs = []
    if since or until:
        q = db.query(Decision).order_by(Decision.timestamp.asc())
        if since:
            q = q.filter(Decision.timestamp >= since)
        if until:
            q = q.filter(Decision.timestamp <= until)
        for d in q.all():
            if d.timestamp:
                delta = d.timestamp - t0
                t_min = max(0, int(delta.total_seconds() // 60))
                decisions_obs.append({
                    "t_min": t_min,
                    "contenu":     _text(d.contenu, anonymize),
                    "responsable": _text(d.responsable, anonymize),
                    "base":        d.base_reglementaire or "",
                })
    else:
        for d in db.query(Decision).order_by(Decision.timestamp.asc()).all():
            if d.timestamp:
                delta = d.timestamp - t0
                t_min = max(0, int(delta.total_seconds() // 60))
                decisions_obs.append({
                    "t_min": t_min,
                    "contenu":     _text(d.contenu, anonymize),
                    "responsable": _text(d.responsable, anonymize),
                    "base":        d.base_reglementaire or "",
                })

    # 6) Durée estimée
    last_t_min = stimuli[-1]["t_min"] if stimuli else 0
    duree_min = max(30, last_t_min + 15)  # marge pour clôturer

    # 7) Objectifs pédagogiques dérivés — basés sur ce qu'a fait l'équipe
    objectifs = _derive_objectifs(stimuli, decisions_obs)

    return {
        "meta": {
            "id":          f"generated_{int(datetime.now(timezone.utc).timestamp())}",
            "titre":       titre,
            "description": description or (
                f"Scénario généré automatiquement à partir d'une crise passée. "
                f"T+0 = {t0.isoformat()}. {len(stimuli)} stimuli reconstitués."
            ),
            "sujet":                 titre,
            "duree_min":             duree_min,
            "duree_reel_min":        duree_min,
            "ratio_compression":     1.0,
            "complexite":            complexite,
            "type_crise":            type_crise,
            "objectifs_pedagogiques": objectifs,
            "categorie":             type_crise.lower(),
            "tags":                  ["généré", "rejouage", "validation-remediation"],
            "nb_stimuli":            len(stimuli),
            # Méta-information : trace que ce scénario vient d'une génération
            # automatique. Utile pour filtrer dans la bibliothèque.
            "generated_from_crisis": True,
            "generated_at":          datetime.now(timezone.utc).isoformat(),
            "anonymized":            bool(anonymize),
        },
        "acteurs": [
            {
                "sigle":             cible_sigle,
                "nom_etablissement": cible_sigle,
                "role":              "coordinateur",
                "port":              8660,
                "joueurs":           [],
            },
            {"sigle": "CERT_SANTE", "nom_etablissement": "CERT Santé",        "port": None, "joueurs": []},
            {"sigle": "ANSSI",      "nom_etablissement": "ANSSI",              "port": None, "joueurs": []},
            {"sigle": "ARS",        "nom_etablissement": "ARS",                "port": None, "joueurs": []},
            {"sigle": "SAMU",       "nom_etablissement": "SAMU",               "port": None, "joueurs": []},
        ],
        "stimuli": stimuli,
        # Bloc complémentaire : ce qui a été FAIT lors de la crise originale.
        # Sert de référence pour évaluer la ré-exécution ("l'équipe a-t-elle
        # pris les mêmes décisions, plus vite, mieux motivées ?").
        "actions_observees": decisions_obs,
    }


def _derive_objectifs(
    stimuli: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
) -> List[str]:
    """Heuristiques pour proposer des objectifs pédagogiques par défaut.
    L'animateur ajustera à la main ensuite.
    """
    obj = []
    types = {s.get("type") for s in stimuli}
    if "incident" in types:
        obj.append("Traiter les incidents dans les délais impartis selon leur urgence")
    if "message" in types:
        obj.append("Coordonner la communication avec les autorités (CERT Santé, ANSSI, ARS, SAMU)")
    if "transfert" in types:
        obj.append("Organiser les transferts patient dans des délais compatibles avec la continuité des soins")
    if decisions:
        obj.append(
            f"Reproduire ou améliorer les {len(decisions)} décisions prises lors de la crise originale"
        )
    obj.append("Valider les mesures de remédiation mises en place depuis la crise originale")
    obj.append("Documenter un REX enrichi (ce qui a changé entre les deux exécutions)")
    return obj


# ─── Sérialisation ───────────────────────────────────────────────────────

def serialize_scenario(scenario: Dict[str, Any]) -> str:
    """Convertit en JSON indenté (format compatible collecteur d'exercice)."""
    return json.dumps(scenario, indent=2, ensure_ascii=False)
