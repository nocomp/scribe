"""
collecteur_exercice/scenario_validator.py — SCRIBE v2.0.2
=========================================================
Validation et auto-correction des scénarios d'exercice.

Utilisé en 3 endroits :
  1. Génération IA (après réponse Albert) : auto-correction + warnings,
     si erreurs bloquantes → 1 retry avec contexte enrichi
  2. Import drag&drop d'un scénario JSON : validation avant écriture
  3. Scan de la liste des scénarios : signalement des fichiers
     incomplets/cassés (avec logger.warning explicite)

Philosophie :
  - On corrige tout ce qu'on peut silencieusement (types, défauts)
  - On signale en warnings ce qu'on a corrigé (pour l'UI animateur)
  - On rejette uniquement ce qui est structurellement bloquant
    (cible inexistante, t_min hors durée, payload vide critique)
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger("scribe.exercice.validator")


# ──────────────────────────────────────────────────────────────────────
# Constantes — typages attendus par les routes SCRIBE
# ──────────────────────────────────────────────────────────────────────

VALID_TYPES = {"incident", "message", "transfert", "decision",
               "capacite", "brancardage", "chat"}

VALID_STATUTS_CAPACITE = {"normal", "tension", "critique", "ferme",
                          "complet", "ok", "insuffisant", "degrade", "hs"}

VALID_PRIORITES_BRC = {"P1", "P2", "P3"}

VALID_TYPES_TRANSPORT = {"BRANCARD", "FAUTEUIL", "AMBULANCE",
                         "MARCHE", "LIT"}

# Espacement minimum recommandé entre stimuli (en t_min simulé). En dessous,
# les stimuli partent quasi simultanément ce qui n'a aucune valeur pédagogique.
# 0.25 = 15s simulées, soit ~4s réelles avec compression x4.
T_MIN_ESPACEMENT_MIN = 0.25


# ──────────────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────────────

def validate_and_fix(scenario: dict, source: str = "import") -> tuple[bool, list[str], list[str], dict]:
    """Valide un scénario, applique les corrections automatiques possibles,
    et retourne :
      - ok (bool) : True si le scénario est jouable après corrections
      - warnings (list[str]) : ce qui a été auto-corrigé (informatif)
      - errors (list[str]) : erreurs bloquantes empêchant le jeu
      - scenario (dict) : scénario corrigé (toujours retourné, modifié in place)

    `source` permet de tracer l'origine (génération IA / import / scan).
    """
    warnings: list[str] = []
    errors: list[str] = []

    # 1. Structure générale
    _validate_structure(scenario, warnings, errors)
    if errors:
        return False, warnings, errors, scenario

    # 2. Acteurs
    sigles_actifs = _validate_acteurs(scenario, warnings, errors)
    if errors:
        return False, warnings, errors, scenario

    # 3. Stimuli — typage, payload, cohérence
    _validate_stimuli(scenario, sigles_actifs, warnings, errors)

    # 4. Timing global
    _validate_timing(scenario, warnings, errors)

    ok = len(errors) == 0
    if warnings:
        logger.info(f"[VALIDATOR/{source}] {len(warnings)} corrections "
                    f"automatiques appliquées sur '{scenario.get('meta',{}).get('id','?')}'")
    if errors:
        logger.warning(f"[VALIDATOR/{source}] {len(errors)} erreurs bloquantes "
                       f"sur '{scenario.get('meta',{}).get('id','?')}': {errors[:3]}")
    return ok, warnings, errors, scenario


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────

def _validate_structure(scenario: dict, warnings: list[str], errors: list[str]) -> None:
    """Vérifie la présence des sections obligatoires."""
    if not isinstance(scenario, dict):
        errors.append("Le scénario n'est pas un objet JSON")
        return
    for key in ("meta", "acteurs", "stimuli"):
        if key not in scenario:
            # On en injecte un vide pour permettre la suite de la validation
            scenario[key] = [] if key != "meta" else {}
            warnings.append(f"Section '{key}' manquante — créée vide")
    if not isinstance(scenario.get("meta"), dict):
        errors.append("La section 'meta' doit être un objet")
    if not isinstance(scenario.get("acteurs"), list):
        errors.append("La section 'acteurs' doit être une liste")
    if not isinstance(scenario.get("stimuli"), list):
        errors.append("La section 'stimuli' doit être une liste")
    if not scenario.get("acteurs"):
        errors.append("Aucun acteur défini — au moins 1 site participant requis")
    if not scenario.get("stimuli"):
        errors.append("Aucun stimulus défini — au moins 1 stimulus requis")
    # Meta : compléments par défaut
    meta = scenario.get("meta", {})
    meta.setdefault("id", "scenario_sans_id")
    meta.setdefault("titre", "Scénario sans titre")
    meta.setdefault("description", "")
    meta.setdefault("duree_min", 60)
    meta.setdefault("duree_reel_min", 240)
    meta.setdefault("ratio_compression", 4.0)
    meta.setdefault("complexite", "MOYEN")
    meta.setdefault("type_crise", "MIXTE")
    # Coercion duree_min en int
    try:
        meta["duree_min"] = int(meta["duree_min"])
    except (ValueError, TypeError):
        meta["duree_min"] = 60
        warnings.append("meta.duree_min invalide — fixé à 60")
    try:
        meta["ratio_compression"] = float(meta["ratio_compression"])
    except (ValueError, TypeError):
        meta["ratio_compression"] = 4.0
        warnings.append("meta.ratio_compression invalide — fixé à 4.0")


def _validate_acteurs(scenario: dict, warnings: list[str], errors: list[str]) -> set[str]:
    """Vérifie la liste des acteurs. Retourne l'ensemble des sigles déclarés."""
    sigles = set()
    for i, a in enumerate(scenario.get("acteurs", [])):
        if not isinstance(a, dict):
            errors.append(f"Acteur #{i} n'est pas un objet")
            continue
        sigle = a.get("sigle")
        if not sigle or not isinstance(sigle, str):
            errors.append(f"Acteur #{i} sans sigle")
            continue
        sigles.add(sigle)
        a.setdefault("nom_etablissement", f"Site {sigle}")
        a.setdefault("role", "joueur")
        a.setdefault("port", 8660 + i)
        a.setdefault("joueurs", [])
    return sigles


def _validate_stimuli(scenario: dict, sigles_actifs: set[str],
                      warnings: list[str], errors: list[str]) -> None:
    """Valide chaque stimulus, applique auto-correction des typages."""
    stimuli = scenario.get("stimuli", [])
    seen_ids = set()
    duree_max = scenario.get("meta", {}).get("duree_min", 60)

    for i, s in enumerate(stimuli):
        if not isinstance(s, dict):
            errors.append(f"Stimulus #{i} n'est pas un objet")
            continue

        # ID
        sid = s.get("id") or f"S{i+1:03d}"
        if not isinstance(sid, str):
            sid = str(sid)
        # Doublon ID → on suffix
        original = sid
        suffix = 1
        while sid in seen_ids:
            sid = f"{original}_dup{suffix}"
            suffix += 1
        if sid != original:
            warnings.append(f"Stimulus #{i} : id '{original}' déjà utilisé — renommé en '{sid}'")
        s["id"] = sid
        seen_ids.add(sid)

        # Type
        stype = s.get("type", "incident")
        if stype not in VALID_TYPES:
            warnings.append(f"Stimulus {sid} : type '{stype}' inconnu — défaut 'incident'")
            stype = "incident"
        s["type"] = stype

        # t_min — coercion en float
        t_min_raw = s.get("t_min", 0)
        try:
            t_min = float(t_min_raw)
            if t_min < 0:
                warnings.append(f"Stimulus {sid} : t_min négatif ({t_min}) → 0")
                t_min = 0.0
            if t_min > duree_max:
                warnings.append(f"Stimulus {sid} : t_min={t_min} > durée scénario ({duree_max}min) "
                                f"— stimulus ne sera pas joué (à corriger)")
        except (ValueError, TypeError):
            warnings.append(f"Stimulus {sid} : t_min '{t_min_raw}' invalide → 0")
            t_min = 0.0
        s["t_min"] = t_min

        # Cible
        cible = s.get("cible")
        if not cible:
            errors.append(f"Stimulus {sid} : pas de cible définie")
            continue
        if cible not in sigles_actifs:
            errors.append(f"Stimulus {sid} : cible '{cible}' n'existe pas dans la liste "
                          f"des acteurs ({', '.join(sorted(sigles_actifs))})")
            continue

        # Titre
        s.setdefault("titre", f"Stimulus {sid}")

        # Payload — validation par type avec auto-correction
        pl = s.get("payload") or {}
        if not isinstance(pl, dict):
            warnings.append(f"Stimulus {sid} : payload invalide — remplacé par {{}}")
            pl = {}
        s["payload"] = pl
        _fix_payload_by_type(sid, stype, pl, warnings, errors)


def _fix_payload_by_type(sid: str, stype: str, pl: dict,
                         warnings: list[str], errors: list[str]) -> None:
    """Auto-correction des payloads selon le type de stimulus."""

    if stype == "incident":
        # Champs obligatoires côté Pydantic IncidentCreate
        if not pl.get("fait"):
            warnings.append(f"Stimulus {sid} (incident) : 'fait' vide — défaut")
            pl["fait"] = "Stimulus exercice"
        # urgency : doit être int 1-4
        urgency = pl.get("urgency", 2)
        try:
            urgency = int(urgency)
        except (ValueError, TypeError):
            warnings.append(f"Stimulus {sid} (incident) : urgency '{urgency}' invalide → 2")
            urgency = 2
        if urgency < 1 or urgency > 4:
            warnings.append(f"Stimulus {sid} (incident) : urgency {urgency} hors plage 1-4 → 2")
            urgency = 2
        pl["urgency"] = urgency
        # impact_fonctionnel : DOIT être bool (sinon Pydantic 422)
        # — c'est LE bug qu'on a découvert hier avec test_exhaustif_42
        impact = pl.get("impact_fonctionnel", False)
        if isinstance(impact, str):
            # Coercion intelligente : strings type "vrai"/"oui"/"true"/"True"/"yes" → True
            if impact.lower() in ("true", "vrai", "oui", "yes", "1"):
                pl["impact_fonctionnel"] = True
            else:
                pl["impact_fonctionnel"] = False
            warnings.append(f"Stimulus {sid} (incident) : impact_fonctionnel converti "
                            f"de string en bool ({pl['impact_fonctionnel']})")
        elif not isinstance(impact, bool):
            pl["impact_fonctionnel"] = bool(impact)
            warnings.append(f"Stimulus {sid} (incident) : impact_fonctionnel converti en bool")
        # type_crise par défaut
        pl.setdefault("type_crise", "MIXTE")
        pl.setdefault("unite_fonctionnelle", "")
        pl.setdefault("declarant_nom", "Animateur exercice")
        pl.setdefault("analyse", "")

    elif stype == "message":
        # Auto-correction : si on a 'expediteur' ET 'sujet' ET 'contenu'
        # on est bon. Sinon on remplit.
        if not pl.get("expediteur") and not pl.get("emetteur"):
            warnings.append(f"Stimulus {sid} (message) : expediteur manquant → 'Acteur externe'")
            pl["expediteur"] = "Acteur externe"
        if not pl.get("sujet"):
            warnings.append(f"Stimulus {sid} (message) : sujet manquant")
            pl["sujet"] = "Message exercice"
        if not pl.get("contenu"):
            warnings.append(f"Stimulus {sid} (message) : contenu manquant")
            pl["contenu"] = "Message externe simulé."

    elif stype == "capacite":
        if not pl.get("unite"):
            errors.append(f"Stimulus {sid} (capacite) : 'unite' obligatoire (UF cible)")
            return
        # Statuts : valeur valide ou 'normal'
        for ch in ("statut_lits", "statut_rh", "statut_materiel"):
            v = pl.get(ch, "normal")
            if not isinstance(v, str) or v not in VALID_STATUTS_CAPACITE:
                warnings.append(f"Stimulus {sid} (capacite) : {ch}='{v}' invalide → 'normal'")
                pl[ch] = "normal"
        pl.setdefault("redacteur", "Animateur exercice")
        pl.setdefault("commentaire_general", "")

    elif stype == "brancardage":
        if not pl.get("uf_origine"):
            warnings.append(f"Stimulus {sid} (brancardage) : uf_origine manquant → 'Urgences'")
            pl["uf_origine"] = "Urgences"
        if not pl.get("uf_destination"):
            warnings.append(f"Stimulus {sid} (brancardage) : uf_destination manquant → 'Imagerie'")
            pl["uf_destination"] = "Imagerie"
        prio = pl.get("priorite", "P2")
        if prio not in VALID_PRIORITES_BRC:
            warnings.append(f"Stimulus {sid} (brancardage) : priorite '{prio}' invalide → P2")
            pl["priorite"] = "P2"
        ttr = pl.get("type_transport", "BRANCARD")
        if ttr not in VALID_TYPES_TRANSPORT:
            warnings.append(f"Stimulus {sid} (brancardage) : type_transport '{ttr}' invalide → BRANCARD")
            pl["type_transport"] = "BRANCARD"
        pl.setdefault("ref_patient", f"EXO-{sid}")
        pl.setdefault("motif", "Transport patient — exercice")

    elif stype == "transfert":
        if not pl.get("etablissement_origine"):
            warnings.append(f"Stimulus {sid} (transfert) : etablissement_origine manquant")
            pl["etablissement_origine"] = "INCONNU"
        if not pl.get("etablissement_destination"):
            warnings.append(f"Stimulus {sid} (transfert) : etablissement_destination manquant")
            pl["etablissement_destination"] = "INCONNU"
        pl.setdefault("unite_origine", "Urgences")
        pl.setdefault("unite_destination", "Réanimation")
        pl.setdefault("motif", "Transfert exercice")
        pl.setdefault("nom", f"Patient EXO-{sid}")
        pl.setdefault("ipp", f"EXO{hash(sid) % 100000:05d}")
        pl.setdefault("statut", "DEMANDE")
        # eta_min coercion en int
        eta = pl.get("eta_min", 30)
        try:
            pl["eta_min"] = int(eta)
        except (ValueError, TypeError):
            warnings.append(f"Stimulus {sid} (transfert) : eta_min '{eta}' invalide → 30")
            pl["eta_min"] = 30

    elif stype == "decision":
        if not pl.get("contenu"):
            warnings.append(f"Stimulus {sid} (decision) : contenu manquant")
            pl["contenu"] = "Décision de cellule de crise (exercice)"
        pl.setdefault("responsable", "Directeur de Crise")
        pl.setdefault("base_reglementaire", "Plan Blanc")


def _validate_timing(scenario: dict, warnings: list[str], errors: list[str]) -> None:
    """Vérifie la cohérence temporelle globale du scénario."""
    stimuli = scenario.get("stimuli", [])
    if not stimuli:
        return
    # Tri par t_min
    stimuli_sorted = sorted(stimuli, key=lambda s: s.get("t_min", 0))
    # Détection de stimuli qui partiraient en rafale (espacement insuffisant)
    rafale_detected = 0
    for i in range(1, len(stimuli_sorted)):
        ecart = stimuli_sorted[i].get("t_min", 0) - stimuli_sorted[i-1].get("t_min", 0)
        if ecart < T_MIN_ESPACEMENT_MIN and ecart >= 0:
            rafale_detected += 1
    if rafale_detected > len(stimuli_sorted) // 3:
        # Plus d'1/3 des stimuli sont en rafale → c'est suspect
        warnings.append(f"Timing serré : {rafale_detected} stimuli espacés "
                        f"de moins de {T_MIN_ESPACEMENT_MIN} min — vérifier la pédagogie")
    # Si TOUS les t_min sont à 0, c'est sûrement un bug de génération IA
    if all(s.get("t_min", 0) == 0 for s in stimuli) and len(stimuli) > 1:
        errors.append("Tous les stimuli ont t_min=0 — la timeline ne peut pas être respectée. "
                      "À régénérer avec des t_min espacés (ex: 0, 5, 10, 15...)")
