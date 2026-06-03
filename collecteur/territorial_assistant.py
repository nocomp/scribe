"""
collecteur_exercice/territorial_assistant.py — v3000h20

Assistant de supervision territoriale.

Conceptuellement différent de l'Assistant par établissement :
- Tourne sur le collecteur (a la vue agrégée des N établissements)
- Détecte des angles morts inter-établissements que personne ne peut voir seul
- 5 règles métier territoriales

API publique :
  evaluate_territorial_rules(etablissements, transferts_inter) -> list[dict]
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger("scribe.collecteur.territorial")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utc(dt_str: str | None) -> datetime | None:
    """Parse ISO datetime tolerant."""
    if not dt_str:
        return None
    try:
        s = dt_str.replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def _is_online(etab: dict) -> bool:
    """Détecte si l'établissement est en ligne (push récent).

    Cherche dans plusieurs champs car la structure varie :
    - 'timestamp' (collecteur exercice)
    - 'received_at' (collecteur prod via /api/summary)
    - 'fresh' (booléen direct du collecteur prod)
    - 'age_minutes' (collecteur prod : < 5 minutes = online)
    """
    # Champ 'fresh' direct (collecteur prod)
    if etab.get("fresh") is True:
        return True
    if etab.get("fresh") is False:
        return False
    # age_minutes
    age = etab.get("age_minutes")
    if isinstance(age, (int, float)):
        return age < 5
    # Timestamp explicite
    ts = _utc(etab.get("timestamp") or etab.get("received_at"))
    if ts:
        return (datetime.now(timezone.utc) - ts).total_seconds() < 300
    # Par défaut : si l'établissement est dans le dict, on le considère online
    # (le collecteur prod ne stocke que ceux qui ont déjà poussé)
    return True


def _nb_critiques(etab: dict) -> int:
    """Nombre d'incidents critiques actifs (U≥3).

    Compatible 2 formats :
    - Format DÉTAILLÉ (collecteur exercice) : liste 'incidents' avec urgency/status
    - Format AGRÉGÉ (collecteur prod) : kpis.incidents_critiques (compteur)
    """
    # Format détaillé : liste d'incidents
    incidents = etab.get("incidents")
    if isinstance(incidents, list) and incidents:
        n = 0
        for inc in incidents:
            if not isinstance(inc, dict):
                continue
            status = (inc.get("status") or "").upper()
            if status in ("RÉSOLU", "RESOLU", "ARCHIVE", "ARCHIVÉ"):
                continue
            urg = inc.get("urgency") or inc.get("urgence") or 1
            if urg >= 3:
                n += 1
        if n > 0 or incidents:  # si la liste existe, on lui fait confiance
            return n
    # Format agrégé : compteur direct
    kpis = etab.get("kpis") or {}
    return int(kpis.get("incidents_critiques", 0) or 0)


def _active_incidents(etab: dict) -> list:
    """Liste des incidents actifs. Si format agrégé, retourne une liste
    factice de N éléments pour que len() donne le bon compteur (les règles
    n'utilisent que le compte, pas les détails).

    v3000h29 — Plus robuste face aux structures inattendues : tente plusieurs
    noms de champs et types.
    """
    incidents = etab.get("incidents")
    if isinstance(incidents, list) and incidents:
        out = []
        for inc in incidents:
            if not isinstance(inc, dict):
                continue
            # Filtrer les résolus / archivés
            status = (inc.get("status") or inc.get("statut") or "").upper()
            if status in ("RÉSOLU", "RESOLU", "ARCHIVE", "ARCHIVÉ", "FERMÉ", "FERME", "CLOS"):
                continue
            out.append(inc)
        # Si la liste contient des incidents non résolus, on les retourne
        if out:
            return out
        # Si la liste existe mais tous les éléments sont filtrés,
        # on retombe sur le compteur kpis pour avoir une estimation
    # Format agrégé : fabriquer liste factice depuis les compteurs
    kpis = etab.get("kpis") or {}
    n_crit = int(kpis.get("incidents_critiques", 0) or 0)
    n_total = int(kpis.get("incidents_ouverts", 0) or 0)
    fake = []
    for _ in range(n_crit):
        fake.append({"urgency": 3, "status": "EN_COURS", "_synthetic": True})
    for _ in range(max(0, n_total - n_crit)):
        fake.append({"urgency": 1, "status": "SIGNALÉ", "_synthetic": True})
    return fake


def _critiques(incidents: list) -> list:
    """Filtre les critiques (U≥3). Tolérant aux variations de nom de champ."""
    out = []
    for i in incidents:
        if not isinstance(i, dict):
            continue
        urg = i.get("urgency") or i.get("urgence") or i.get("priority") or 1
        try:
            urg = int(urg)
        except (TypeError, ValueError):
            urg = 1
        if urg >= 3:
            out.append(i)
    return out


def _has_decla_active(etab: dict, niveau_min: int = 2, type_crise: str | None = None) -> bool:
    """Cherche une déclaration active dans cet établissement de niveau >= niveau_min."""
    for d in (etab.get("declarations") or []):
        if not isinstance(d, dict):
            continue
        if not d.get("actif", True):
            continue
        if (d.get("niveau_tension") or 1) < niveau_min:
            continue
        if type_crise:
            tc = (d.get("type_crise") or "").lower()
            if tc != type_crise.lower():
                continue
        return True
    return False


def _has_plan_blanc(etab: dict) -> bool:
    """L'établissement a-t-il activé un Plan Blanc ?

    Un Plan Blanc est une DÉCISION FORMELLE prise par le dircrise, pas un
    niveau de tension automatique. On le détecte UNIQUEMENT via :
    1. Une déclaration explicite de type 'plan blanc'
    2. Une déclaration de niveau de tension 3 (= crise déclarée par humain)

    On NE PAS considérer 'niveau_global == CRISE/CRITIQUE' comme Plan Blanc :
    ces niveaux sont calculés automatiquement depuis les urgences incidents,
    pas activés par le dircrise.

    v3000h30 — Bug fix : la version précédente considérait niveau_global=CRISE
    comme Plan Blanc, ce qui faisait que RT1 ne se déclenchait jamais en prod
    quand les 3 établissements étaient en CRITIQUE (mais sans PB déclaré).
    """
    # 1. Déclaration de type plan_blanc explicite
    for d in (etab.get("declarations") or []):
        if not isinstance(d, dict):
            continue
        tc = (d.get("type_crise") or "").lower()
        if "plan" in tc and "blanc" in tc:
            return True
    # 2. Indication via niveau_tension 3 (= crise DÉCLARÉE par humain dans
    #    une déclaration active, pas le niveau auto-calculé)
    for d in (etab.get("declarations") or []):
        if not isinstance(d, dict):
            continue
        if d.get("actif", True) and (d.get("niveau_tension") or 0) >= 3:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Règles territoriales
# ─────────────────────────────────────────────────────────────────────────────

def rule_t1_evenement_territorial(etabs_online: list[dict]) -> list[dict]:
    """RT1 — Évènement territorial probable : ≥3 établissements ont des U≥3
    actifs simultanément sans Plan Blanc activé partout.

    Signal fort : si plusieurs établissements sont touchés en même temps,
    c'est probablement un événement coordonné qui dépasse chaque acteur seul.
    """
    affectes = []
    for e in etabs_online:
        crit = _critiques(_active_incidents(e))
        if len(crit) >= 1:
            affectes.append({
                "sigle": e.get("sigle"),
                "nb_critiques": len(crit),
                "plan_blanc": _has_plan_blanc(e),
            })
    if len(affectes) < 3:
        return []
    sans_pb = [a for a in affectes if not a["plan_blanc"]]
    if not sans_pb:
        return []
    sigles = ", ".join(sorted(a["sigle"] for a in affectes))
    return [{
        "rule_id": "evenement_territorial",
        "niveau":  "alert",
        "titre":   "⚠️ Événement territorial probable",
        "message": (
            f"{len(affectes)} établissements signalent simultanément des incidents "
            f"critiques (U≥3) : {sigles}. "
            f"{len(sans_pb)} d'entre eux n'ont pas activé de Plan Blanc. "
            f"Cette concomitance suggère un événement à signaler comme tel "
            f"à l'ARS de région (niveau territorial)."
        ),
        "etablissements_concernes": [a["sigle"] for a in affectes],
        "actions": [
            {"label": "Voir détail établissements", "type": "highlight_sites"},
            {"label": "Modèle déclaration ARS territoriale", "type": "show_template"},
        ],
    }]


def rule_t2_transfert_incoherent(etabs_online: list[dict], transferts_inter: list[dict]) -> list[dict]:
    """RT2 — Transfert accepté vers un établissement déclaré en saturation.

    Le donneur d'ordre n'a pas pu voir que le destinataire venait de déclarer
    une tension critique. C'est la situation 14h17 du récit immersif.
    """
    alertes = []
    # Map sigle → est-il en saturation ?
    saturation_sigles = set()
    for e in etabs_online:
        # Critère "saturation" : a une déclaration niveau≥3 OU statut_lits=critique
        decl_critique = any(
            isinstance(d, dict) and d.get("actif", True) and (d.get("niveau_tension") or 0) >= 3
            for d in (e.get("declarations") or [])
        )
        # Critère secondaire : niveau_global ROUGE et nb_incidents ≥ 2
        niveau = (e.get("niveau_global") or "").upper()
        if decl_critique or (niveau in ("ROUGE", "CRITIQUE") and e.get("nb_incidents_actifs", 0) >= 2):
            saturation_sigles.add(e.get("sigle"))

    if not saturation_sigles:
        return []

    # Parcourir les transferts récents vers ces sigles
    now = datetime.now(timezone.utc)
    for tr in (transferts_inter or []):
        if not isinstance(tr, dict):
            continue
        # Transfert récent uniquement (< 30 min)
        tr_ts = _utc(tr.get("timestamp") or tr.get("horodatage_creation"))
        if tr_ts and (now - tr_ts).total_seconds() > 1800:
            continue
        statut = (tr.get("statut") or "").upper()
        if statut not in ("ACCEPTE", "ACCEPTÉ", "EN_COURS"):
            continue
        dest = tr.get("ght_destinataire") or tr.get("etablissement_destination") or ""
        if dest in saturation_sigles:
            emetteur = tr.get("ght_emetteur") or tr.get("etablissement_source") or "?"
            alertes.append({
                "rule_id": f"transfert_incoherent_{tr.get('id', 'x')}",
                "niveau":  "alert",
                "titre":   "⚠️ Transfert vers un établissement saturé",
                "message": (
                    f"Transfert de {emetteur} vers {dest} (statut {statut}). "
                    f"{dest} a déclaré une tension critique. L'information n'est "
                    f"peut-être pas remontée jusqu'au donneur d'ordre."
                ),
                "etablissements_concernes": [emetteur, dest],
                "actions": [
                    {"label": "Voir le transfert", "type": "highlight_transfert", "payload": {"id": tr.get("id")}},
                ],
            })
    return alertes


def rule_t3_plan_blanc_absent(etabs_online: list[dict]) -> list[dict]:
    """RT3 — Aucun établissement n'a Plan Blanc activé alors que ≥4 ont des U≥3."""
    affectes = [e for e in etabs_online if len(_critiques(_active_incidents(e))) >= 1]
    if len(affectes) < 4:
        return []
    with_pb = [e for e in affectes if _has_plan_blanc(e)]
    if with_pb:
        return []  # au moins un PB activé
    sigles = sorted(e.get("sigle") for e in affectes)
    return [{
        "rule_id": "plan_blanc_territorial_absent",
        "niveau":  "alert",
        "titre":   "⚠️ Plan Blanc absent dans tout le territoire",
        "message": (
            f"{len(affectes)} établissements ({', '.join(sigles)}) ont des "
            f"incidents critiques actifs, AUCUN n'a activé son Plan Blanc. "
            f"Décision territoriale à formaliser sans délai."
        ),
        "etablissements_concernes": sigles,
        "actions": [
            {"label": "Modèle activation Plan Blanc GHT", "type": "show_template"},
        ],
    }]


def rule_t4_etablissement_isole(etabs_online: list[dict], transferts_inter: list[dict]) -> list[dict]:
    """RT4 — Un établissement a des incidents critiques mais n'a sollicité
    aucun autre établissement du GHT (transfert ou demande).

    Symptôme classique d'isolement : on essaie de tout gérer seul.
    """
    if len(etabs_online) < 2:
        return []
    # Pour chaque établissement, ses U≥3 actifs
    alertes = []
    now = datetime.now(timezone.utc)
    for e in etabs_online:
        sigle = e.get("sigle")
        crit = _critiques(_active_incidents(e))
        if len(crit) < 2:  # seuil : au moins 2 incidents critiques
            continue
        # A-t-il émis un transfert ou une demande dans les 30 dernières min ?
        sollicitations = 0
        for tr in (transferts_inter or []):
            if not isinstance(tr, dict):
                continue
            if (tr.get("ght_emetteur") or "") != sigle:
                continue
            tr_ts = _utc(tr.get("timestamp") or tr.get("horodatage_creation"))
            if tr_ts and (now - tr_ts).total_seconds() < 1800:
                sollicitations += 1
        # Vérifier aussi les "demandes" remontées dans le payload
        for dem in (e.get("demandes") or []):
            if isinstance(dem, dict):
                dem_ts = _utc(dem.get("created_at") or dem.get("timestamp"))
                if dem_ts and (now - dem_ts).total_seconds() < 1800:
                    sollicitations += 1
        if sollicitations == 0:
            alertes.append({
                "rule_id": f"isolement_{sigle}",
                "niveau":  "marker",
                "titre":   f"Établissement isolé : {sigle}",
                "message": (
                    f"{sigle} signale {len(crit)} incidents critiques actifs "
                    f"mais n'a sollicité aucun établissement voisin dans les "
                    f"30 dernières minutes. Vérifier les capacités de délestage."
                ),
                "etablissements_concernes": [sigle],
                "actions": [
                    {"label": "Voir " + sigle, "type": "highlight_site", "payload": {"sigle": sigle}},
                ],
            })
    return alertes


def rule_t5_declaration_inhomogene(etabs_online: list[dict]) -> list[dict]:
    """RT5 — Hétérogénéité des déclarations : certains établissements en VEILLE
    alors que d'autres sont en CRISE pour le même type d'événement.

    Signal de mauvaise coordination territoriale.
    """
    if len(etabs_online) < 3:
        return []
    # Map sigle → niveau max actif de chaque type de crise
    niveaux_par_type: dict[str, dict[str, int]] = {}
    for e in etabs_online:
        sigle = e.get("sigle")
        for d in (e.get("declarations") or []):
            if not isinstance(d, dict) or not d.get("actif", True):
                continue
            tc = (d.get("type_crise") or "").lower()
            nv = d.get("niveau_tension") or 1
            niveaux_par_type.setdefault(tc, {})[sigle] = max(niveaux_par_type.get(tc, {}).get(sigle, 0), nv)

    out = []
    for tc, niveaux in niveaux_par_type.items():
        if len(niveaux) < 2:
            continue
        vmax = max(niveaux.values())
        vmin = min(niveaux.values())
        if vmax >= 3 and vmin <= 1:
            sigles_haut = sorted(s for s, v in niveaux.items() if v >= 3)
            sigles_bas  = sorted(s for s, v in niveaux.items() if v <= 1)
            out.append({
                "rule_id": f"declaration_inhomogene_{tc}",
                "niveau":  "marker",
                "titre":   f"Hétérogénéité déclaration {tc.upper()}",
                "message": (
                    f"Sur ce type de crise ({tc}) : "
                    f"{', '.join(sigles_haut)} déclarent en CRISE alors que "
                    f"{', '.join(sigles_bas)} sont en VIGILANCE. "
                    f"Alignement territorial à clarifier."
                ),
                "etablissements_concernes": sigles_haut + sigles_bas,
                "actions": [],
            })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Évaluation globale
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_territorial_rules(
    etablissements: dict[str, dict],
    transferts_inter: list[dict],
) -> dict:
    """Évalue toutes les règles territoriales et retourne un dict structuré
    avec les alertes + un résumé d'état territorial.
    """
    etabs_online = [e for e in etablissements.values() if _is_online(e)]
    total_etabs = len(etablissements)
    nb_online = len(etabs_online)

    # Stats globales
    nb_incidents_total = sum(len(_active_incidents(e)) for e in etabs_online)
    nb_critiques_total = sum(len(_critiques(_active_incidents(e))) for e in etabs_online)
    nb_pb = sum(1 for e in etabs_online if _has_plan_blanc(e))
    nb_with_critiques = sum(
        1 for e in etabs_online if _critiques(_active_incidents(e))
    )

    alertes: list[dict] = []
    for fn in (
        rule_t1_evenement_territorial,
        rule_t3_plan_blanc_absent,
        rule_t5_declaration_inhomogene,
    ):
        try:
            alertes.extend(fn(etabs_online))
        except Exception as e:
            logger.warning(f"Règle {fn.__name__} échouée : {e}")
    # Règles qui ont besoin aussi des transferts
    for fn in (rule_t2_transfert_incoherent, rule_t4_etablissement_isole):
        try:
            alertes.extend(fn(etabs_online, transferts_inter))
        except Exception as e:
            logger.warning(f"Règle {fn.__name__} échouée : {e}")

    # Trier : alert avant marker
    niveau_rank = {"alert": 0, "marker": 1, "silent": 2}
    alertes.sort(key=lambda a: niveau_rank.get(a.get("niveau"), 1))

    return {
        "summary": {
            "total_etablissements":      total_etabs,
            "etablissements_online":     nb_online,
            "etablissements_avec_critiques": nb_with_critiques,
            "incidents_total":           nb_incidents_total,
            "incidents_critiques_total": nb_critiques_total,
            "plans_blancs_actifs":       nb_pb,
        },
        "alertes": alertes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
