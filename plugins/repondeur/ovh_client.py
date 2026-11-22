"""
plugins/repondeur/ovh_client.py — SCRIBE
=========================================
Couche d'accès OVH Télécom pour le plugin RÉPONDEUR (fournisseur alternatif à
Twilio).

Différence de modèle, assumée :
  - Twilio sert le message en LIVE via un webhook TwiML <Say> → changer le texte
    en base suffit.
  - OVH ne fait pas de TTS « à la volée » par webhook : le message du SVI /
    pré-décroché se règle dans l'espace client OVH (saisie d'un texte synthétisé
    par OVH, ou fichier audio). SCRIBE reste la SOURCE UNIQUE du texte (saisie,
    import depuis FICHIERS, rédaction assistée) et fournit ce texte prêt à coller,
    en vérifiant que le compte OVH est joignable.

Auth OVH : signature SHA1("$as+$ck+$method+$url+$body+$ts"), identique à la
passerelle SMS OVH déjà utilisée par SCRIBE (plugins/notifications/backends/sms).

Le déchiffrement des secrets réutilise enc/dec de twilio_client (clé dérivée de
SCRIBE_SECRET).
"""
import os
import logging

from plugins.repondeur.twilio_client import enc, dec, mask_secret  # noqa: F401

logger = logging.getLogger("scribe.plugins.repondeur")

OVH_ENDPOINTS = {
    "ovh-eu": "https://eu.api.ovh.com/1.0",
    "ovh-ca": "https://ca.api.ovh.com/1.0",
}


def endpoint_url(endpoint: str) -> str:
    return OVH_ENDPOINTS.get((endpoint or "ovh-eu"), OVH_ENDPOINTS["ovh-eu"])


# ── Résolution de configuration : local > central 'ovh_voice' > env ──────────
def _central() -> dict:
    try:
        from app.central_config import get_domain
        d = get_domain("ovh_voice")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def get_config(db=None) -> dict:
    """Config OVH effective (secrets déchiffrés)."""
    row = None
    if db is not None:
        try:
            from plugins.repondeur.models import RepondeurConfig
            row = db.query(RepondeurConfig).filter_by(id=1).first()
        except Exception:
            row = None
    central = _central()

    def pick(local_val, central_key, env_key, default=""):
        if local_val:
            return local_val
        cv = central.get(central_key) if central else None
        if cv:
            return cv
        return os.getenv(env_key, default)

    return {
        "endpoint":        pick(getattr(row, "ovh_endpoint", None), "endpoint", "SCRIBE_OVH_ENDPOINT", "ovh-eu"),
        "app_key":         pick(getattr(row, "ovh_app_key", None), "app_key", "SCRIBE_OVH_APP_KEY"),
        "app_secret":      pick(dec(getattr(row, "ovh_app_secret", "") or ""), "app_secret", "SCRIBE_OVH_APP_SECRET"),
        "consumer_key":    pick(dec(getattr(row, "ovh_consumer_key", "") or ""), "consumer_key", "SCRIBE_OVH_CONSUMER_KEY"),
        "billing_account": pick(getattr(row, "ovh_billing_account", None), "billing_account", "SCRIBE_OVH_BILLING"),
        "service":         pick(getattr(row, "ovh_service", None), "service", "SCRIBE_OVH_SERVICE"),
    }


def is_configured(db=None) -> bool:
    c = get_config(db)
    return bool(c["app_key"] and c["app_secret"] and c["consumer_key"])


def _svc_name(numero: str, cfg: dict = None) -> str:
    """Numéro → serviceName OVH. OVH attend le format « 0033XXXXXXXXX »
    (00 + indicatif), pas « +33… »."""
    s = (numero or (cfg.get("service") if cfg else "") or "").strip()
    if s.startswith("+"):
        s = "00" + s[1:]
    return s.replace(" ", "").replace(".", "")


_BILLING_CACHE = {}


def _resolve_billing(cfg: dict, numero: str) -> str:
    """Compte de facturation (billingAccount). Si non renseigné, on le DÉCOUVRE
    via l'API : /telephony (liste des comptes) puis /telephony/{ba}/service pour
    trouver celui qui contient le numéro. Mémoïsé."""
    billing = (cfg.get("billing_account") or "").strip()
    if billing:
        return billing
    svc = _svc_name(numero, cfg)
    if not svc:
        return ""
    if svc in _BILLING_CACHE:
        return _BILLING_CACHE[svc]
    try:
        code, bas = _signed_request(cfg, "GET", "/telephony")
        if code == 200 and isinstance(bas, list):
            for ba in bas:
                try:
                    c2, svcs = _signed_request(cfg, "GET", f"/telephony/{ba}/service")
                    if c2 == 200 and isinstance(svcs, list) and svc in svcs:
                        _BILLING_CACHE[svc] = ba
                        return ba
                except Exception:
                    pass
            # numéro non trouvé mais un seul compte → on le prend par défaut
            if len(bas) == 1:
                _BILLING_CACHE[svc] = bas[0]
                return bas[0]
    except Exception:
        pass
    return ""


def source_of(field: str, row) -> str:
    """D'où vient la valeur effective : local / central / env / défaut."""
    local_map = {
        "endpoint": "ovh_endpoint", "app_key": "ovh_app_key",
        "app_secret": "ovh_app_secret", "consumer_key": "ovh_consumer_key",
        "billing_account": "ovh_billing_account", "service": "ovh_service",
    }
    if row is not None and getattr(row, local_map.get(field, field), None):
        return "local"
    c = _central()
    if c.get(field):
        return "central"
    env_map = {
        "endpoint": "SCRIBE_OVH_ENDPOINT", "app_key": "SCRIBE_OVH_APP_KEY",
        "app_secret": "SCRIBE_OVH_APP_SECRET", "consumer_key": "SCRIBE_OVH_CONSUMER_KEY",
        "billing_account": "SCRIBE_OVH_BILLING", "service": "SCRIBE_OVH_SERVICE",
    }
    if env_map.get(field) and os.getenv(env_map[field]):
        return "env"
    return "default"


# ── Requête OVH signée (sync httpx) ──────────────────────────────────────────
_TIME_CACHE = {"delta": None}


def _ovh_now(cfg) -> str:
    """Horodatage aligné sur OVH (offset calculé une fois puis réutilisé —
    évite un appel /auth/time à chaque requête, plus rapide pour la démo)."""
    import time
    if _TIME_CACHE["delta"] is None:
        try:
            import httpx
            base = endpoint_url(cfg["endpoint"])
            with httpx.Client(timeout=6.0) as c:
                srv = int(c.get(base + "/auth/time").text.strip())
            _TIME_CACHE["delta"] = srv - int(time.time())
        except Exception:
            _TIME_CACHE["delta"] = 0
    return str(int(time.time()) + _TIME_CACHE["delta"])


def _signed_request(cfg: dict, method: str, path: str, body: str = "") -> "tuple":
    """Exécute une requête signée OVH. Retourne (status_code, json|text).
    `path` peut contenir une query string déjà encodée (incluse dans la signature)."""
    import hashlib
    import httpx
    base = endpoint_url(cfg["endpoint"])
    url = base + path
    ts = _ovh_now(cfg)
    sig_raw = f"{cfg['app_secret']}+{cfg['consumer_key']}+{method}+{url}+{body}+{ts}"
    sig = "$1$" + hashlib.sha1(sig_raw.encode()).hexdigest()
    headers = {
        "X-Ovh-Application": cfg["app_key"],
        "X-Ovh-Consumer":    cfg["consumer_key"],
        "X-Ovh-Timestamp":   ts,
        "X-Ovh-Signature":   sig,
        "Content-Type":      "application/json",
    }
    with httpx.Client(timeout=12.0) as client:
        r = client.request(method, url, content=(body or None), headers=headers)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text


def test_credentials(db=None) -> dict:
    """Vérifie les identifiants OVH via GET /me. Retourne {ok, mode, detail}."""
    cfg = get_config(db)
    if not is_configured(db):
        return {"ok": False, "mode": "dev",
                "detail": "Identifiants OVH absents (mode DEV) — clé app/secret/consumer requis."}
    try:
        code, data = _signed_request(cfg, "GET", "/me")
        if code == 200 and isinstance(data, dict):
            who = data.get("nichandle") or data.get("email") or "compte OVH"
            return {"ok": True, "mode": "live", "detail": f"Compte OVH « {who} » joignable."}
        if code in (401, 403):
            return {"ok": False, "mode": "live",
                    "detail": "OVH a refusé les identifiants (clé/consumer non validés ou droits insuffisants)."}
        return {"ok": False, "mode": "live", "detail": f"OVH a répondu {code}."}
    except Exception as e:
        return {"ok": False, "mode": "live", "detail": f"Échec d'appel OVH : {e}"}


def list_voicemail(db=None) -> dict:
    """Best-effort : liste les services de messagerie vocale du compte de
    facturation, pour aider l'opérateur à repérer la ligne à configurer.
    Tolérant : renvoie {ok, items|detail}."""
    cfg = get_config(db)
    if not is_configured(db) or not cfg["billing_account"]:
        return {"ok": False, "detail": "Compte de facturation OVH non renseigné."}
    try:
        code, data = _signed_request(
            cfg, "GET", f"/telephony/{cfg['billing_account']}/voicemail")
        if code == 200 and isinstance(data, list):
            return {"ok": True, "items": data}
        return {"ok": False, "detail": f"OVH a répondu {code}."}
    except Exception as e:
        return {"ok": False, "detail": f"Échec d'appel OVH : {e}"}


def call_stats(db=None, ligne=None) -> dict:
    """Statistiques d'appels OVH pour une ligne (le numéro sert de serviceName).

    Interroge /telephony/{billingAccount}/service/{serviceName}/voiceConsumption
    (la longueur du tableau = nombre de communications). Best-effort ET très
    défensif : ne lève jamais, renvoie ok=False proprement si indisponible
    (mauvais type de ligne, droits API, aucune donnée…). Robuste pour un live.
    """
    import datetime as _dt
    cfg = get_config(db)
    numero  = (getattr(ligne, "numero", None) or cfg.get("service") or "").strip()
    billing = _resolve_billing(cfg, numero)
    now = _dt.datetime.now(_dt.timezone.utc)
    out = {"ok": False, "provider": "ovh", "numero": numero,
           "calls_today": None, "calls_total": None,
           "at": now.strftime("%H:%M")}
    if not is_configured(db) or not billing or not numero:
        out["detail"] = "Compte OVH / numéro non résolu (clés ou numéro à vérifier)."
        return out
    svc = _svc_name(numero, cfg)
    base_path = f"/telephony/{billing}/service/{svc}/voiceConsumption"

    def _iso(d):
        return d.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1) Appels du jour (filtré sur la date de création)
    try:
        from urllib.parse import urlencode
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        q = urlencode({"creationDatetime.from": _iso(start),
                       "creationDatetime.to":   _iso(now)})
        code, data = _signed_request(cfg, "GET", base_path + "?" + q)
        if code == 200 and isinstance(data, list):
            out["calls_today"] = len(data)
            out["ok"] = True
    except Exception:
        pass

    # 2) Total disponible (non filtré) — contexte / repli
    try:
        code, data = _signed_request(cfg, "GET", base_path)
        if code == 200 and isinstance(data, list):
            out["calls_total"] = len(data)
            out["ok"] = True
    except Exception:
        pass

    if not out["ok"]:
        out["detail"] = "Statistiques indisponibles pour cette ligne."
    return out


def list_calls(db=None, ligne=None, today_only: bool = True, limit: int = 60) -> dict:
    """Détail des communications de la ligne (appelant, date, durée, sens).
    Défensif : renvoie {ok, calls:[...]} ou {ok:False, detail}."""
    import datetime as _dt
    cfg = get_config(db)
    numero  = (getattr(ligne, "numero", None) or cfg.get("service") or "").strip()
    billing = _resolve_billing(cfg, numero)
    if not is_configured(db) or not billing or not numero:
        return {"ok": False, "detail": "Compte OVH / numéro non résolu."}
    svc = _svc_name(numero, cfg)
    base = f"/telephony/{billing}/service/{svc}/voiceConsumption"
    now = _dt.datetime.now(_dt.timezone.utc)
    ids = []
    try:
        path = base
        if today_only:
            from urllib.parse import urlencode
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            q = urlencode({"creationDatetime.from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "creationDatetime.to":   now.strftime("%Y-%m-%dT%H:%M:%SZ")})
            path = base + "?" + q
        code, data = _signed_request(cfg, "GET", path)
        if code == 200 and isinstance(data, list):
            ids = data
        elif code in (401, 403):
            return {"ok": False, "detail": "Droits API insuffisants."}
    except Exception as e:
        return {"ok": False, "detail": f"Échec d'appel OVH : {e}"}
    ids = ids[:limit]
    calls = []
    for cid in ids:
        item = {"id": cid, "calling": "", "called": "", "date": "", "duration": None, "way": ""}
        try:
            c2, m = _signed_request(cfg, "GET", f"{base}/{cid}")
            if c2 == 200 and isinstance(m, dict):
                item["calling"]  = m.get("calling") or m.get("callingNumber") or ""
                item["called"]   = m.get("called") or m.get("calledNumber") or ""
                item["date"]     = m.get("creationDatetime") or m.get("date") or ""
                item["duration"] = m.get("duration")
                item["way"]      = m.get("wayType") or ""
        except Exception:
            pass
        calls.append(item)
    return {"ok": True, "count": len(calls), "calls": calls}


def count_voicemail(db=None, ligne=None) -> int:
    """Nombre de messages vocaux (léger : une seule requête). 0 si indispo."""
    cfg = get_config(db)
    numero = (getattr(ligne, "numero", None) or cfg.get("service") or "")
    base = _vm_base(cfg, numero)
    if not base:
        return 0
    try:
        code, data = _signed_request(cfg, "GET", base + "/directories")
        if code == 200 and isinstance(data, list):
            return len(data)
    except Exception:
        pass
    return 0


def _vm_base(cfg: dict, numero: str):
    """Chemin de base de la messagerie vocale OVH pour un numéro, ou None."""
    billing = _resolve_billing(cfg, numero)
    svc = _svc_name(numero, cfg)
    if not billing or not svc:
        return None
    return f"/telephony/{billing}/voicemail/{svc}"


def list_voicemail_messages(db=None, ligne=None, limit: int = 50) -> dict:
    """Liste les messages vocaux laissés sur la ligne (métadonnées).

    /telephony/{billing}/voicemail/{service}/directories → identifiants des
    messages ; puis /directories/{id} → détail. Très défensif : ne lève jamais.
    Prérequis : la ligne doit être en MESSAGERIE VOCALE côté OVH (sinon aucun
    message n'est enregistré).
    """
    cfg = get_config(db)
    numero = (getattr(ligne, "numero", None) or cfg.get("service") or "")
    base = _vm_base(cfg, numero)
    if not is_configured(db) or not base:
        return {"ok": False, "detail": "Compte OVH / numéro non renseigné."}

    ids = []
    try:
        code, data = _signed_request(cfg, "GET", base + "/directories")
        if code == 200 and isinstance(data, list):
            ids = list(data)
        elif code in (400, 404):
            # Certains comptes exigent le paramètre de dossier : repli.
            for d in ("0", "1", "2"):
                try:
                    c2, d2 = _signed_request(cfg, "GET", base + "/directories?dir=" + d)
                    if c2 == 200 and isinstance(d2, list):
                        ids.extend(d2)
                except Exception:
                    pass
        elif code in (401, 403):
            return {"ok": False, "detail": "Droits API insuffisants (voicemail)."}
    except Exception as e:
        return {"ok": False, "detail": f"Échec d'appel OVH : {e}"}

    # Dédup en conservant l'ordre
    seen, uniq = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i); uniq.append(i)
    uniq = uniq[:limit]

    messages = []
    for mid in uniq:
        item = {"id": mid, "caller": "", "date": "", "duration": None}
        try:
            code, m = _signed_request(cfg, "GET", f"{base}/directories/{mid}")
            if code == 200 and isinstance(m, dict):
                item["caller"]   = m.get("callerIdNumber") or m.get("caller") or ""
                item["date"]     = m.get("creationDatetime") or m.get("date") or ""
                item["duration"] = m.get("duration")
        except Exception:
            pass
        messages.append(item)
    return {"ok": True, "count": len(messages), "messages": messages}


def voicemail_download_ref(db=None, ligne=None, mid=None, fmt: str = "mp3"):
    """Retourne (url_temporaire, filename) pour télécharger l'audio d'un message,
    ou None. OVH renvoie une URL temporaire (à récupérer ensuite sans signature)."""
    cfg = get_config(db)
    numero = (getattr(ligne, "numero", None) or cfg.get("service") or "")
    base = _vm_base(cfg, numero)
    if not base or mid is None:
        return None
    try:
        from urllib.parse import urlencode
        q = urlencode({"format": fmt})
        code, data = _signed_request(cfg, "GET", f"{base}/directories/{mid}/download?{q}")
        if code == 200 and isinstance(data, dict) and data.get("url"):
            return data.get("url"), (data.get("filename") or f"message_{mid}.{fmt}")
    except Exception:
        pass
    return None


def voicemail_fetch_audio(db=None, ligne=None, mid=None, fmt: str = "mp3"):
    """Télécharge l'audio d'un message et renvoie (bytes, filename, mimetype),
    ou None. Réutilisé par le téléchargement ET la transcription locale."""
    ref = voicemail_download_ref(db, ligne, mid, fmt=fmt)
    if not ref:
        return None
    url, filename = ref
    try:
        import httpx
        r = httpx.get(url, timeout=30.0)
        if r.status_code != 200:
            return None
        media = "audio/ogg" if filename.lower().endswith(".ogg") else "audio/mpeg"
        return r.content, filename, media
    except Exception:
        return None


def voicemail_transcript(db=None, ligne=None, mid=None) -> dict:
    """Transcription d'un message vocal (si activée côté OVH). Best-effort."""
    cfg = get_config(db)
    numero = (getattr(ligne, "numero", None) or cfg.get("service") or "")
    base = _vm_base(cfg, numero)
    if not base or mid is None:
        return {"ok": False, "detail": "Message introuvable."}
    try:
        code, data = _signed_request(cfg, "GET", f"{base}/directories/{mid}/transcript")
        if code == 200:
            if isinstance(data, str):
                return {"ok": True, "text": data}
            if isinstance(data, dict):
                return {"ok": True, "text": data.get("transcript") or data.get("text") or ""}
            if isinstance(data, list):
                return {"ok": True, "text": "\n".join(str(x) for x in data)}
        if code in (400, 404):
            return {"ok": False, "detail": "Transcription non activée côté OVH pour ce message. "
                    "Activez la retranscription dans les réglages de la messagerie (espace client OVH)."}
        return {"ok": False, "detail": f"OVH a répondu {code}."}
    except Exception as e:
        return {"ok": False, "detail": f"Échec d'appel OVH : {e}"}


def apply_guidance(ligne, langues_textes: dict, db=None) -> dict:
    """Mode assisté : retourne le texte prêt à coller dans le SVI OVH + des
    consignes claires. Vérifie au passage la joignabilité du compte OVH.

    langues_textes : { "fr": "Bonjour…", "en": "Hello…" }
    """
    cfg = get_config(db)
    blocs = []
    for code, txt in langues_textes.items():
        if (txt or "").strip():
            blocs.append(f"[{code.upper()}] {txt.strip()}")
    script = "\n\n".join(blocs) or "(aucun message saisi)"
    reachable = is_configured(db)
    detail = ("Compte OVH configuré — collez ce texte dans le message du SVI / "
              "pré-décroché du numéro, dans l'espace client OVH (Télécom → votre "
              "numéro → SVI / Répondeur → Message d'accueil). OVH synthétise le "
              "texte en voix, ou vous pouvez téléverser un fichier audio.")
    if not reachable:
        detail = ("Identifiants OVH non renseignés (mode DEV). Le texte ci-dessous "
                  "est prêt à être collé dans le SVI OVH une fois le compte configuré.")
    return {
        "ok": True,
        "provider": "ovh",
        "mode": "live" if reachable else "dev",
        "numero": ligne.numero or "",
        "billing_account": cfg["billing_account"],
        "service": cfg["service"],
        "script": script,
        "detail": detail,
    }
