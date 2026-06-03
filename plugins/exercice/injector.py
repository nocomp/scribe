"""
plugins/exercice/injector.py — Injecteur de stimuli asynchrone
Tourne en background, respecte le timing compressé du scénario.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("scribe.exercice.injector")

# ── État global de l'injecteur ────────────────────────────────────────────────
_state = {
    "running":      False,
    "paused":       False,
    "session_uid":  None,
    "scenario":     None,
    "t_start":      None,        # datetime UTC du début
    "t_paused_s":   0,           # secondes accumulées en pause
    "pause_start":  None,        # datetime du début de la pause courante
    "stimuli_done": [],          # ids stimulus injectés
    "stimuli_error": [],         # ids stimulus en erreur
}

_task: Optional[asyncio.Task] = None


def get_state() -> dict:
    """Retourne l'état courant de l'injecteur (pour l'API /status)."""
    elapsed = _get_elapsed_s()
    scenario = _state["scenario"] or {}
    ratio = scenario.get("meta", {}).get("ratio_compression", 4.0)
    stimuli = scenario.get("stimuli", [])
    return {
        "running":       _state["running"],
        "paused":        _state["paused"],
        "session_uid":   _state["session_uid"],
        "scenario_titre": scenario.get("meta", {}).get("titre", ""),
        "t_elapsed_s":   elapsed,
        "t_elapsed_min": round(elapsed / 60, 1),
        "ratio_compression": ratio,
        "stimuli_total": len(stimuli),
        "stimuli_done":  len(_state["stimuli_done"]),
        "stimuli_error": len(_state["stimuli_error"]),
        "stimuli_status": [
            {
                "id": s["id"],
                "t_min": s["t_min"],
                "type": s["type"],
                "cible": s["cible"],
                "done": s["id"] in _state["stimuli_done"],
                "error": s["id"] in _state["stimuli_error"],
                "t_restant_s": max(0, int(s["t_min"] * 60 / ratio) - elapsed),
            }
            for s in stimuli
        ],
    }


def _get_elapsed_s() -> int:
    """Retourne les secondes écoulées dans le scénario (pause déduite)."""
    if not _state["t_start"] or not _state["running"]:
        return _state.get("t_elapsed_frozen", 0)
    now = datetime.now(timezone.utc)
    total = (now - _state["t_start"]).total_seconds()
    paused = _state["t_paused_s"]
    if _state["paused"] and _state["pause_start"]:
        paused += (now - _state["pause_start"]).total_seconds()
    return max(0, int(total - paused))


def start(scenario: dict, session_uid: str, token: str, base_urls: dict) -> bool:
    """
    Démarre l'injecteur en background.
    base_urls : {sigle: "http://vps:8660", ...}
    """
    global _task
    if _state["running"]:
        return False
    _state.update({
        "running": True, "paused": False,
        "session_uid": session_uid, "scenario": scenario,
        "t_start": datetime.now(timezone.utc),
        "t_paused_s": 0, "pause_start": None,
        "stimuli_done": [], "stimuli_error": [],
        "t_elapsed_frozen": 0,
    })
    loop = asyncio.get_event_loop()
    _task = loop.create_task(_run(scenario, session_uid, token, base_urls))
    logger.info(f"Injecteur démarré — session {session_uid}")
    return True


def pause() -> bool:
    if not _state["running"] or _state["paused"]:
        return False
    _state["paused"] = True
    _state["pause_start"] = datetime.now(timezone.utc)
    logger.info("Injecteur mis en pause")
    return True


def resume() -> bool:
    if not _state["running"] or not _state["paused"]:
        return False
    if _state["pause_start"]:
        _state["t_paused_s"] += (datetime.now(timezone.utc) - _state["pause_start"]).total_seconds()
    _state["paused"] = False
    _state["pause_start"] = None
    logger.info("Injecteur repris")
    return True


def stop() -> bool:
    global _task
    if not _state["running"]:
        return False
    _state["t_elapsed_frozen"] = _get_elapsed_s()
    _state["running"] = False
    _state["paused"] = False
    if _task and not _task.done():
        _task.cancel()
    logger.info("Injecteur arrêté")
    return True


async def inject_one(stimulus_id: str, token: str, base_urls: dict) -> dict:
    """Injection manuelle d'un stimulus (par l'animateur)."""
    scenario = _state.get("scenario")
    if not scenario:
        return {"ok": False, "error": "Aucun scénario actif"}
    stimulus = next((s for s in scenario.get("stimuli", []) if s["id"] == stimulus_id), None)
    if not stimulus:
        return {"ok": False, "error": f"Stimulus {stimulus_id} non trouvé"}
    result = await _inject_stimulus(stimulus, token, base_urls, manuel=True)
    return result


# ── Boucle principale ─────────────────────────────────────────────────────────

async def _run(scenario: dict, session_uid: str, token: str, base_urls: dict):
    """Boucle principale : attend le timing de chaque stimulus et l'injecte."""
    stimuli = sorted(scenario.get("stimuli", []), key=lambda s: s["t_min"])
    ratio = scenario.get("meta", {}).get("ratio_compression", 4.0)

    for stimulus in stimuli:
        if not _state["running"]:
            break
        # Attendre le bon moment (temps compressé)
        target_s = int(stimulus["t_min"] * 60 / ratio)
        while True:
            if not _state["running"]:
                return
            # Attente si pause
            while _state["paused"]:
                await asyncio.sleep(2)
            elapsed = _get_elapsed_s()
            if elapsed >= target_s:
                break
            await asyncio.sleep(3)

        if stimulus["id"] in _state["stimuli_done"]:
            continue  # déjà injecté manuellement
        await _inject_stimulus(stimulus, token, base_urls)

    logger.info(f"Scénario terminé — session {session_uid}")
    _state["running"] = False


async def _inject_stimulus(stimulus: dict, token: str, base_urls: dict, manuel: bool = False) -> dict:
    """Injecte un stimulus sur l'instance cible."""
    sigle = stimulus.get("cible", "DEMO1")
    base_url = base_urls.get(sigle)
    if not base_url:
        logger.error(f"URL inconnue pour {sigle}")
        _state["stimuli_error"].append(stimulus["id"])
        return {"ok": False, "error": f"URL inconnue pour {sigle}"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Exercice-Session": _state.get("session_uid", ""),
        "X-Exercice-Stimulus": stimulus["id"],
    }
    payload = stimulus.get("payload", {})
    stype = stimulus.get("type", "incident")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if stype == "incident":
                r = await client.post(
                    f"{base_url}/api/v1/sitrep/post",
                    json=payload, headers=headers
                )
            elif stype == "message":
                r = await client.post(
                    f"{base_url}/api/v1/messagerie/send",
                    json=payload, headers=headers
                )
            elif stype == "transfert":
                # v2182 : le stimulus transfert doit déclencher la même
                # chaîne qu'en mode nominal : POST local pour créer la fiche
                # côté source, PUIS push au collecteur pour que le destinataire
                # voie le transfert entrant dans son Kanban (avec l'ambulance
                # sur le chemin comme en prod). Sans ce push, l'équipe
                # destinataire a un incident mais pas la fiche kanban.
                #
                # v2184 : injection de défauts robustes pour que le stimulus
                # ne casse pas si le scénario n'a pas explicitement mis tous
                # les champs obligatoires de TransfertCreate.
                payload = dict(payload)  # ne pas muter le scénario chargé
                payload.setdefault("etablissement_origine", sigle)
                payload.setdefault("redacteur", "Animateur (stimulus exercice)")
                payload.setdefault("statut", "EN_COURS")
                payload.setdefault("nom", "Patient exercice")
                payload.setdefault("ipp", "EXO-" + stimulus.get("id", "?"))
                if "motif" in payload and "commentaire" not in payload:
                    payload["commentaire"] = "Motif: " + payload["motif"]
                r = await client.post(
                    f"{base_url}/api/v1/transferts",
                    json=payload, headers=headers
                )
                if r.status_code < 300:
                    try:
                        created = r.json()
                        await _push_transfert_to_collecteur(client, base_url,
                                                             sigle, created, headers)
                    except Exception as e:
                        logger.warning(
                            f"Transfert {stimulus['id']} créé localement OK "
                            f"mais push collecteur KO: {e}"
                        )
                else:
                    logger.warning(
                        f"Transfert {stimulus['id']} POST local KO "
                        f"({r.status_code}): {r.text[:200]} "
                        f"— payload: {payload}"
                    )
            elif stype == "chat":
                # Message dans un salon chat spécifique
                salon_id = payload.get("salon_id", 1)
                r = await client.post(
                    f"{base_url}/api/v1/chat/salons/{salon_id}/messages",
                    json={"contenu": payload.get("contenu", ""), "mentions": []},
                    headers=headers
                )
            elif stype == "capacite":
                # Mise à jour capacité d'une UF
                r = await client.put(
                    f"{base_url}/api/v1/capacite/update",
                    json=payload, headers=headers
                )
            elif stype == "decision":
                r = await client.post(
                    f"{base_url}/api/v1/cellule/decisions",
                    json=payload, headers=headers
                )
            else:
                logger.warning(f"Type de stimulus inconnu: {stype}")
                return {"ok": False, "error": f"Type inconnu: {stype}"}

        ok = r.status_code < 300
        if ok:
            _state["stimuli_done"].append(stimulus["id"])
            logger.info(f"Stimulus {stimulus['id']} ({stype}) → {sigle} : OK {r.status_code}")
        else:
            _state["stimuli_error"].append(stimulus["id"])
            logger.warning(f"Stimulus {stimulus['id']} → {sigle} : {r.status_code} {r.text[:200]}")

        return {"ok": ok, "status_code": r.status_code, "manuel": manuel}

    except Exception as e:
        logger.error(f"Erreur injection {stimulus['id']} → {sigle}: {e}")
        _state["stimuli_error"].append(stimulus["id"])
        return {"ok": False, "error": str(e)}


async def _push_transfert_to_collecteur(client, base_url: str, sigle_emetteur: str,
                                         created: dict, headers: dict) -> None:
    """v2182 — Propage un transfert nouvellement créé au collecteur d'exercice,
    exactement comme le front le fait après trPushCollecteur en mode nominal.
    Récupère la config fédération via l'instance émettrice, puis POST sur
    /api/push-transfert. L'instance destinataire verra le transfert entrant
    au prochain polling de loadTransfertsEntrants() (toutes les 12s).
    """
    # Récupérer collecteur_url + token via l'API de l'instance
    fed_r = await client.get(
        f"{base_url}/api/v1/federation/status", headers=headers
    )
    if fed_r.status_code >= 300:
        raise RuntimeError(f"federation/status {fed_r.status_code}")
    fed = fed_r.json()
    if not fed.get("ready") or not fed.get("collecteur_url"):
        raise RuntimeError("fédération non configurée sur l'instance")
    coll_base = fed["collecteur_url"].replace("/api/push", "")
    fed_token = fed.get("token", "")
    if not fed_token:
        raise RuntimeError("token fédération absent")

    # Déterminer le sigle destinataire depuis le payload de retour
    etab_dest = created.get("etablissement_destination") or ""
    # Le front utilise .toUpperCase() — on fait pareil pour cohérence
    ght_dest = etab_dest.upper() if etab_dest else ""

    push_payload = {
        "id_local":                   created.get("id"),
        "ght_emetteur_nom":           sigle_emetteur,
        "ght_destinataire":           ght_dest,
        "unite_origine":              created.get("unite_origine", ""),
        "etablissement_origine":      created.get("etablissement_origine", ""),
        "unite_destination":          created.get("unite_destination", ""),
        "etablissement_destination":  created.get("etablissement_destination", ""),
        "site_destination":           created.get("site_destination") or created.get("etablissement_destination", ""),
        "statut":                     created.get("statut", "EN_PREPARATION"),
        "eta":                        created.get("eta"),
        "horodatage_depart":          created.get("horodatage_depart"),
        "commentaire":                created.get("commentaire", ""),
    }
    push_r = await client.post(
        f"{coll_base}/api/push-transfert",
        json=push_payload,
        headers={"Authorization": f"Bearer {fed_token}",
                 "Content-Type": "application/json"},
    )
    if push_r.status_code >= 300:
        raise RuntimeError(f"push-transfert {push_r.status_code}: {push_r.text[:120]}")
    logger.info(f"Transfert {created.get('id')} poussé au collecteur → {ght_dest}")
