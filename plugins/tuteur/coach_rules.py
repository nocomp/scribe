"""
plugins/tuteur/coach_rules.py — v3.1.0

Moteur de règles déterministes du copilote.

Philosophie v3.1 :
- AUCUNE règle basée sur le silence de l'utilisateur (banni : un utilisateur
  silencieux est probablement au téléphone).
- Règles basées sur les INCOHÉRENCES INTERNES et les OBLIGATIONS MANQUANTES.
- 3 niveaux d'intrusion : silent | marker | alert.

Les 7 règles :
  R1. Incident U≥3 SIGNALÉ depuis >10 min sans tâche associée    → marker
  R2. Incident CYBER actif sans décision ANSSI/CERT-Santé        → marker
  R3. Incident SANITAIRE U≥3 sans déclaration de situation       → marker
  R4. Déclaration VEILLE alors qu'incident(s) U3 actif(s)        → ALERT
  R5. Capacité 100% déclarée + ≥1 transfert entrant accepté      → ALERT
  R6. Pas de Plan Blanc alors que ≥3 incidents U3 simultanés     → ALERT
  R7. Pôle critique attendu absent (cyber 30min sans DPI/IMAG)   → marker

API publique :
  evaluate_all_rules(db, session_id) -> List[dict]
    Chaque dict = {rule_id, priorite, type_msg, niveau, message,
                   actions_json, target_type, target_id}
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, List

from sqlalchemy.orm import Session

from plugins.tuteur.models import TuteurCoachMessage
from app.models import (
    SitrepEntry, Task, Decision,
    TransfertPatient, DeclarationSituation,
    CapaciteDeclaration,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _minutes_since(dt: datetime | None) -> float:
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (_utcnow() - dt).total_seconds() / 60.0


def _has_recent_active_message(
    db: Session, session_id: int, rule_id: str,
    target_type: str | None = None, target_id: int | None = None,
    window_min: int = 15,
) -> bool:
    """v3000h18 — Anti-spam ESCALADÉ : silence croissant après chaque rappel.

    Stratégie :
      - 0 émission → autorise (return False = pas spam)
      - 1 émission → silence 1h (60 min)
      - 2 émissions → silence 3h (180 min)
      - 3 émissions ou plus → silence DÉFINITIF pour cette session/cible

    Cela évite le défilement répétitif observé en h17 (8 fois le même message)
    et respecte le choix du dircrise : si malgré 3 rappels il ne fait pas
    l'action, c'est qu'il a un motif (exercice de test, décision consciente).
    Le bouton "Plus tard" pose lui un snooze explicite (snooze_until).

    Le paramètre window_min de l'ancienne signature est conservé pour
    rétro-compatibilité mais ignoré : c'est l'escalade qui décide.
    """
    # Compter les rappels existants pour cette règle/cible dans la session
    q = db.query(TuteurCoachMessage).filter(
        TuteurCoachMessage.session_id == session_id,
        TuteurCoachMessage.rule_id == rule_id,
    )
    if target_type is not None:
        q = q.filter(TuteurCoachMessage.target_type == target_type)
    if target_id is not None:
        q = q.filter(TuteurCoachMessage.target_id == target_id)

    rappels = q.order_by(TuteurCoachMessage.created_at.desc()).all()
    n = len(rappels)

    # 3 ou plus → silence définitif (sauf si tous ack)
    if n >= 3:
        return True
    if n == 0:
        return False

    # Sinon : silence = 1h après le 1er, 3h après le 2ème
    silence_minutes = 60 if n == 1 else 180
    dernier = rappels[0]
    age = _minutes_since(dernier.created_at)
    return age < silence_minutes


def _active_incidents(db: Session) -> List[SitrepEntry]:
    """Incidents non archivés et non résolus."""
    return (
        db.query(SitrepEntry)
        .filter(
            SitrepEntry.archived == False,  # noqa: E712
            SitrepEntry.status != "RÉSOLU",
        )
        .all()
    )


def _action_buttons(incident_id: int | None = None) -> List[dict]:
    """Boutons d'action standard pour un message lié à un incident.

    v3000h18 — Boutons systématiques :
      • Voir l'incident (navigation)
      • ✨ Créer 3 tâches (action proactive)
      • Plus tard (snooze 1h, plus long que avant)
      • Pas pertinent (snooze 24h = silence quasi-définitif)
    """
    btns = []
    if incident_id:
        btns.append({
            "label": "📋 Voir l'incident",
            "action_type": "open_tab",
            "payload": {"tab": "tab-veille", "incident_id": incident_id, "highlight": True},
        })
        btns.append({
            "label": "✨ Créer 3 tâches",
            "action_type": "generate_tasks",
            "payload": {"incident_id": incident_id},
        })
    btns.append({
        "label": "Plus tard",
        "action_type": "snooze",
        "payload": {"minutes": 60},  # v3000h18 : 10min → 60min, signal plus respecté
    })
    btns.append({
        "label": "Pas pertinent",
        "action_type": "snooze",
        "payload": {"minutes": 1440},  # v3000h18 : 24h = silence pour la journée
    })
    return btns


# ─────────────────────────────────────────────────────────────────────────────
# R1 — Incident U≥3 SIGNALÉ depuis >10 min sans tâche associée
# ─────────────────────────────────────────────────────────────────────────────

def rule_incident_critique_sans_tache(
    db: Session, session_id: int, *, is_exercice: bool = False,
) -> List[dict]:
    seuil_min = 3 if is_exercice else 10
    candidats = []
    for inc in _active_incidents(db):
        if (inc.urgency or 1) < 3:
            continue
        if (inc.status or "") != "SIGNALÉ":
            continue
        if _minutes_since(inc.timestamp) < seuil_min:
            continue
        # Vérifier qu'aucune tâche n'est liée à cet incident
        nb_tasks = db.query(Task).filter(Task.incident_id == inc.id).count()
        if nb_tasks > 0:
            continue
        # Anti-spam
        if _has_recent_active_message(
            db, session_id, "incident_critique_sans_tache",
            target_type="incident", target_id=inc.id,
        ):
            continue
        libelle = (inc.fait or "(sans titre)")[:80]
        candidats.append({
            "rule_id":      "incident_critique_sans_tache",
            "priorite":     2,
            "type_msg":     "warning",
            "niveau":       "marker",
            "message":      (
                f"Incident U{inc.urgency} signalé depuis "
                f"{int(_minutes_since(inc.timestamp))} min sans tâche associée : "
                f"« {libelle} »"
            ),
            "actions_json": _action_buttons(inc.id),
            "target_type":  "incident",
            "target_id":    inc.id,
        })
    return candidats


# ─────────────────────────────────────────────────────────────────────────────
# R2 — Incident CYBER actif sans décision ANSSI/CERT-Santé
# ─────────────────────────────────────────────────────────────────────────────

_CYBER_KEYWORDS = ("ANSSI", "CERT", "CERT-SANTE", "CERT-SANTÉ", "FSSI")

def rule_cyber_sans_notification(
    db: Session, session_id: int, *, is_exercice: bool = False,
) -> List[dict]:
    seuil_min = 5 if is_exercice else 15
    cyber = [
        i for i in _active_incidents(db)
        if (i.type_crise or "").upper() == "CYBER"
        and _minutes_since(i.timestamp) >= seuil_min
    ]
    if not cyber:
        return []
    # Une seule alerte globale (pas par incident) tant qu'aucune notification tracée
    decisions = db.query(Decision).all()
    for d in decisions:
        contenu = (d.contenu or "").upper()
        if any(k in contenu for k in _CYBER_KEYWORDS):
            return []  # Notification déjà tracée
    if _has_recent_active_message(db, session_id, "cyber_sans_notification"):
        return []
    inc_principal = cyber[0]
    return [{
        "rule_id":      "cyber_sans_notification",
        "priorite":     3,
        "type_msg":     "warning",
        "niveau":       "marker",
        "obligation_id": "anssi_incident_cyber",  # v3000h18 — KB ref
        "message":      (
            f"Crise cyber active depuis {int(_minutes_since(inc_principal.timestamp))} min. "
            f"Aucune notification ANSSI / CERT-Santé tracée. Obligation réglementaire."
        ),
        "actions_json": [
            {"label": "📋 Voir l'incident", "action_type": "open_tab",
             "payload": {"tab": "tab-veille", "incident_id": inc_principal.id, "highlight": True}},
            {"label": "✨ Créer 3 tâches", "action_type": "generate_tasks",
             "payload": {"incident_id": inc_principal.id}},
            {"label": "📞 Aide ANSSI", "action_type": "show_obligation",
             "payload": {"obligation_id": "anssi_incident_cyber",
                         "incident_id": inc_principal.id}},
            {"label": "Plus tard", "action_type": "snooze", "payload": {"minutes": 60}},
        ],
        "target_type":  "incident",
        "target_id":    inc_principal.id,
    }]


# ─────────────────────────────────────────────────────────────────────────────
# R3 — Incident SANITAIRE U≥3 sans déclaration de situation
# ─────────────────────────────────────────────────────────────────────────────

def rule_sanitaire_sans_declaration(
    db: Session, session_id: int, *, is_exercice: bool = False,
) -> List[dict]:
    seuil_min = 5 if is_exercice else 15
    sanitaires = [
        i for i in _active_incidents(db)
        if (i.type_crise or "").upper() in ("SANITAIRE", "MIXTE")
        and (i.urgency or 1) >= 3
        and _minutes_since(i.timestamp) >= seuil_min
    ]
    if not sanitaires:
        return []
    # Cherche une déclaration de situation SANITAIRE active de niveau ≥ 2
    decla = (
        db.query(DeclarationSituation)
        .filter(DeclarationSituation.actif == True)  # noqa: E712
        .filter(DeclarationSituation.type_crise.in_(["sanitaire", "SANITAIRE"]))
        .order_by(DeclarationSituation.created_at.desc())
        .first()
    )
    if decla is not None and (decla.niveau_tension or 1) >= 2:
        return []
    if _has_recent_active_message(db, session_id, "sanitaire_sans_declaration"):
        return []
    inc_principal = sanitaires[0]
    decla_label = "aucune déclaration active" if not decla else f"niveau {decla.niveau_tension}"
    return [{
        "rule_id":      "sanitaire_sans_declaration",
        "priorite":     3,
        "type_msg":     "warning",
        "niveau":       "marker",
        "obligation_id": "ars_tension_sanitaire",  # v3000h18 — KB ref
        "message":      (
            f"{len(sanitaires)} incident(s) sanitaire(s) U≥3 actif(s). "
            f"Déclaration de situation sanitaire : {decla_label}. "
            f"Envisager une déclaration de tension à l'ARS."
        ),
        "actions_json": [
            {"label": "📋 Voir l'incident", "action_type": "open_tab",
             "payload": {"tab": "tab-veille", "incident_id": inc_principal.id, "highlight": True}},
            {"label": "✨ Créer 3 tâches", "action_type": "generate_tasks",
             "payload": {"incident_id": inc_principal.id}},
            {"label": "📞 Aide ARS", "action_type": "show_obligation",
             "payload": {"obligation_id": "ars_tension_sanitaire",
                         "incident_id": inc_principal.id}},
            {"label": "Plus tard", "action_type": "snooze", "payload": {"minutes": 60}},
        ],
        "target_type":  "incident",
        "target_id":    inc_principal.id,
    }]


# ─────────────────────────────────────────────────────────────────────────────
# R4 — ALERT — Déclaration VEILLE alors qu'incident(s) U3 actif(s)
# ─────────────────────────────────────────────────────────────────────────────

def rule_contradiction_declaration_veille(
    db: Session, session_id: int, *, is_exercice: bool = False,
) -> List[dict]:
    # Cherche une déclaration de situation active en VIGILANCE (niveau_tension=1)
    # alors qu'il y a des incidents U3.
    decla = (
        db.query(DeclarationSituation)
        .filter(DeclarationSituation.actif == True)  # noqa: E712
        .order_by(DeclarationSituation.created_at.desc())
        .first()
    )
    if decla is None:
        return []
    if (decla.niveau_tension or 1) != 1:
        return []  # déjà en tension ou crise, pas de contradiction
    u3_actifs = [i for i in _active_incidents(db) if (i.urgency or 1) >= 3]
    if not u3_actifs:
        return []
    if _has_recent_active_message(db, session_id, "contradiction_veille_u3"):
        return []
    return [{
        "rule_id":      "contradiction_veille_u3",
        "priorite":     3,
        "type_msg":     "critique",
        "niveau":       "alert",
        "message":      (
            f"⚠️ Contradiction : déclaration de situation en « vigilance » "
            f"alors que {len(u3_actifs)} incident(s) U3 actif(s). À réévaluer."
        ),
        "actions_json": [
            {"label": "📋 Voir les incidents", "action_type": "open_tab",
             "payload": {"tab": "tab-veille"}},
            {"label": "Plus tard", "action_type": "snooze", "payload": {"minutes": 10}},
        ],
        "target_type":  "declaration",
        "target_id":    decla.id,
    }]


# ─────────────────────────────────────────────────────────────────────────────
# R5 — ALERT — Capacité 100% déclarée + ≥1 transfert entrant accepté
# ─────────────────────────────────────────────────────────────────────────────

def rule_contradiction_capacite_transfert(
    db: Session, session_id: int, *, is_exercice: bool = False,
) -> List[dict]:
    # Cherche les déclarations capacité récentes en saturation/critique
    # (utilise tension_activee == 2 OU statut_lits == 'critique'/'ferme')
    cutoff = _utcnow() - timedelta(hours=2)
    decls_critiques = (
        db.query(CapaciteDeclaration)
        .filter(CapaciteDeclaration.horodatage >= cutoff)
        .filter(
            (CapaciteDeclaration.tension_activee >= 2) |
            (CapaciteDeclaration.statut_lits.in_(["critique", "ferme"]))
        )
        .all()
    )
    if not decls_critiques:
        return []
    # Transferts entrants acceptés (vers cet établissement)
    # Le modèle TransfertPatient n'a pas forcément un champ "sens", on regarde
    # juste les transferts ACCEPTE/EN_COURS récents.
    transferts_recents = (
        db.query(TransfertPatient)
        .filter(TransfertPatient.statut.in_(["ACCEPTE", "EN_COURS"]))
        .count()
    )
    if transferts_recents == 0:
        return []
    if _has_recent_active_message(db, session_id, "contradiction_capacite_transfert"):
        return []
    return [{
        "rule_id":      "contradiction_capacite_transfert",
        "priorite":     3,
        "type_msg":     "critique",
        "niveau":       "alert",
        "message":      (
            f"⚠️ Contradiction : capacité déclarée en tension critique "
            f"({len(decls_critiques)} déclaration(s)) alors que "
            f"{transferts_recents} transfert(s) en cours. "
            f"Cohérence à vérifier."
        ),
        "actions_json": [
            {"label": "📋 Voir transferts", "action_type": "open_tab",
             "payload": {"tab": "tab-transferts"}},
            {"label": "📊 Voir capacité", "action_type": "open_tab",
             "payload": {"tab": "tab-capacite"}},
            {"label": "Plus tard", "action_type": "snooze", "payload": {"minutes": 10}},
        ],
        "target_type":  "capacite",
        "target_id":    None,
    }]


# ─────────────────────────────────────────────────────────────────────────────
# R6 — ALERT — Pas de Plan Blanc alors que ≥3 incidents U3 simultanés
# ─────────────────────────────────────────────────────────────────────────────

_PLAN_BLANC_KEYWORDS = ("PLAN BLANC", "PLANBLANC", "PB ACTIVÉ", "PB ACTIVE")

def rule_pas_de_plan_blanc(
    db: Session, session_id: int, *, is_exercice: bool = False,
) -> List[dict]:
    u3_actifs = [i for i in _active_incidents(db) if (i.urgency or 1) >= 3]
    if len(u3_actifs) < 3:
        return []
    # Vérifier déclaration formelle Plan Blanc
    decla_pb = (
        db.query(DeclarationSituation)
        .filter(DeclarationSituation.actif == True)  # noqa: E712
        .filter(DeclarationSituation.type_crise.in_(["plan_blanc", "PLAN_BLANC", "PLANBLANC"]))
        .first()
    )
    if decla_pb is not None:
        return []
    # Fallback : vérifier dans les décisions textuelles
    decisions = db.query(Decision).all()
    for d in decisions:
        contenu = (d.contenu or "").upper()
        if any(k in contenu for k in _PLAN_BLANC_KEYWORDS):
            return []
    if _has_recent_active_message(db, session_id, "pas_de_plan_blanc"):
        return []
    return [{
        "rule_id":      "pas_de_plan_blanc",
        "priorite":     3,
        "type_msg":     "critique",
        "niveau":       "alert",
        "message":      (
            f"⚠️ {len(u3_actifs)} incidents U3 simultanés. "
            f"Aucune activation du Plan Blanc tracée. "
            f"À formaliser (décision + déclaration de situation) pour traçabilité."
        ),
        "actions_json": [
            {"label": "📋 Voir incidents", "action_type": "open_tab",
             "payload": {"tab": "tab-veille"}},
            {"label": "Plus tard", "action_type": "snooze", "payload": {"minutes": 15}},
        ],
        "target_type":  None,
        "target_id":    None,
    }]


# ─────────────────────────────────────────────────────────────────────────────
# R7 — Pôle critique attendu absent (cyber 30min sans DPI/IMAGERIE)
# ─────────────────────────────────────────────────────────────────────────────

# Mapping type_crise → pôles attendus dans les incidents
_POLES_ATTENDUS = {
    "CYBER": ["DPI", "IMAGERIE", "LABO", "TÉLÉPHONIE", "PACS", "SI"],
    # Pour SANITAIRE massif, on ne peut pas généraliser : trop dépendant du scénario
}

def rule_pole_critique_absent(
    db: Session, session_id: int, *, is_exercice: bool = False,
) -> List[dict]:
    seuil_min = 10 if is_exercice else 30
    cyber = [
        i for i in _active_incidents(db)
        if (i.type_crise or "").upper() == "CYBER"
    ]
    if not cyber:
        return []
    # Plus vieil incident cyber actif
    cyber_age = max((_minutes_since(i.timestamp) for i in cyber), default=0)
    if cyber_age < seuil_min:
        return []
    # Pôles déjà mentionnés dans les incidents actifs
    poles_mentionnes = set()
    for inc in _active_incidents(db):
        uf = (inc.unite_fonctionnelle or "").upper()
        fait = (inc.fait or "").upper()
        for p in _POLES_ATTENDUS["CYBER"]:
            if p in uf or p in fait:
                poles_mentionnes.add(p)
    attendus = set(_POLES_ATTENDUS["CYBER"])
    manquants = attendus - poles_mentionnes
    if len(manquants) >= 4:
        # Si la quasi-totalité des pôles attendus sont absents, c'est probablement
        # un scénario où ce mapping ne s'applique pas. On reste silencieux.
        return []
    if not manquants:
        return []
    if _has_recent_active_message(db, session_id, "pole_critique_absent"):
        return []
    liste = ", ".join(sorted(manquants)[:4])
    return [{
        "rule_id":      "pole_critique_absent",
        "priorite":     1,
        "type_msg":     "info",
        "niveau":       "marker",
        "message":      (
            f"Crise cyber depuis {int(cyber_age)} min. "
            f"Angle mort possible : aucun incident remonté sur {liste}. "
            f"Vérifier l'impact sur ces services."
        ),
        "actions_json": [
            {"label": "Plus tard", "action_type": "snooze", "payload": {"minutes": 15}},
            {"label": "Ignorer",   "action_type": "dismiss", "payload": {}},
        ],
        "target_type":  None,
        "target_id":    None,
    }]


# ─────────────────────────────────────────────────────────────────────────────
# Évaluation globale
# ─────────────────────────────────────────────────────────────────────────────

ALL_RULES = [
    rule_incident_critique_sans_tache,    # R1
    rule_cyber_sans_notification,         # R2
    rule_sanitaire_sans_declaration,      # R3
    rule_contradiction_declaration_veille,# R4 alert
    rule_contradiction_capacite_transfert,# R5 alert
    rule_pas_de_plan_blanc,               # R6 alert
    rule_pole_critique_absent,            # R7
]


def evaluate_all_rules(
    db: Session, session_id: int, *, is_exercice: bool = False,
) -> List[dict]:
    """Évalue toutes les règles et retourne la liste de candidats messages."""
    out: List[dict] = []
    for fn in ALL_RULES:
        try:
            out.extend(fn(db, session_id, is_exercice=is_exercice))
        except Exception as e:
            import logging
            logging.getLogger("scribe.tuteur.rules").warning(
                f"Règle {fn.__name__} a échoué : {e}"
            )
    # Tri : alert > marker > silent ; puis priorite décroissante
    niveau_rank = {"alert": 0, "marker": 1, "silent": 2}
    out.sort(key=lambda m: (niveau_rank.get(m.get("niveau", "marker"), 1),
                            -m.get("priorite", 2)))
    return out
