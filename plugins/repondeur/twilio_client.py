"""
plugins/repondeur/twilio_client.py — SCRIBE
============================================
Couche d'accès Twilio pour le plugin RÉPONDEUR.

  - Résolution de configuration : table locale `plugin_repondeur_config`
    > config CENTRALE 'twilio' (supervision) > env SCRIBE_TWILIO_*.
  - Chiffrement au repos de l'auth_token (Fernet, clé dérivée de SCRIBE_SECRET ;
    préfixe `enc:`). Repli clair si `cryptography` absent.
  - Construction du TwiML lu par Twilio à chaque appel (rien n'est « poussé »
    chez Twilio : le message est servi dynamiquement par SCRIBE → le mettre à
    jour en base suffit, l'appelant suivant l'entend).
  - Helpers REST optionnels : test des identifiants, déclaration du webhook voix
    sur un numéro (provisioning). En l'absence d'identifiants → mode DEV (aucun
    appel réseau).

Aucune dépendance au SDK Twilio : appels REST via httpx (déjà utilisé par SCRIBE).
"""
import os
import base64
import hashlib
import logging
import xml.sax.saxutils as _sax

logger = logging.getLogger("scribe.plugins.repondeur")

_ENC_PREFIX = "enc:"

# ── Mapping code SCRIBE (2 lettres) → langue/voix Twilio <Say> ───────────────
# Twilio attend des codes BCP-47 (fr-FR…). Voix Amazon Polly recommandées quand
# disponibles ; repli sur la voix générique sinon.
TWILIO_LANG = {
    "fr": "fr-FR", "en": "en-US", "de": "de-DE", "es": "es-ES", "it": "it-IT",
    "nl": "nl-NL", "pl": "pl-PL", "pt": "pt-PT", "sv": "sv-SE", "da": "da-DK",
    "fi": "fi-FI", "el": "el-GR", "cs": "cs-CZ", "ro": "ro-RO", "ru": "ru-RU",
    "no": "nb-NO", "ga": "en-IE", "hu": "hu-HU", "bg": "bg-BG", "hr": "hr-HR",
    "sk": "sk-SK", "sl": "sl-SI", "lt": "lt-LT", "lv": "lv-LV", "et": "et-EE",
    "mt": "en-GB", "ca": "ca-ES",
}

# Invite « tapez N » par langue (pour le pré-menu SVI multilingue).
PROMPT_PRESS = {
    "fr": "Pour le français, tapez {n}.",
    "en": "For English, press {n}.",
    "de": "Für Deutsch, drücken Sie {n}.",
    "es": "Para español, marque {n}.",
    "it": "Per l'italiano, digita {n}.",
    "pt": "Para português, prima {n}.",
    "nl": "Voor Nederlands, druk op {n}.",
    "pl": "Aby wybrać polski, naciśnij {n}.",
}


def twilio_lang(code: str) -> str:
    return TWILIO_LANG.get((code or "fr").lower()[:2], "en-US")


# ── Chiffrement (Fernet si dispo) ────────────────────────────────────────────
def _fernet():
    try:
        from cryptography.fernet import Fernet
        secret = os.getenv("SCRIBE_SECRET") or os.getenv("ADMIN_TOKEN") or "scribe-default-key"
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)
    except Exception:
        return None


def enc(value: str) -> str:
    if not value:
        return ""
    f = _fernet()
    if not f:
        return value
    try:
        return _ENC_PREFIX + f.encrypt(value.encode()).decode()
    except Exception:
        return value


def dec(value: str) -> str:
    if not value or not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value or ""
    f = _fernet()
    if not f:
        return value
    try:
        return f.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except Exception:
        return ""


# ── Résolution de configuration ──────────────────────────────────────────────
def _central() -> dict:
    try:
        from app.central_config import get_domain
        d = get_domain("twilio")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def get_config(db=None) -> dict:
    """Config effective : local > central > env. auth_token EN CLAIR (déchiffré)."""
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

    account_sid = pick(getattr(row, "account_sid", None), "account_sid", "SCRIBE_TWILIO_SID")
    auth_token  = pick(dec(getattr(row, "auth_token", "") or ""), "auth_token", "SCRIBE_TWILIO_TOKEN")
    public_url  = pick(getattr(row, "public_url", None), "public_url", "SCRIBE_PUBLIC_URL")
    voice       = pick(getattr(row, "default_voice", None), "default_voice", "SCRIBE_TWILIO_VOICE", "alice")

    return {
        "account_sid": account_sid or "",
        "auth_token":  auth_token or "",
        "public_url":  (public_url or "").rstrip("/"),
        "default_voice": voice or "alice",
    }


def is_live(db=None) -> bool:
    cfg = get_config(db)
    return bool(cfg["account_sid"] and cfg["auth_token"])


def current_mode(db=None) -> str:
    return "live" if is_live(db) else "dev"


def source_of(field: str, row) -> str:
    """D'où vient la valeur effective d'un champ : local / central / env / défaut."""
    if row is not None and getattr(row, field, None):
        return "local"
    c = _central()
    if c.get(field):
        return "central"
    env_map = {"account_sid": "SCRIBE_TWILIO_SID", "auth_token": "SCRIBE_TWILIO_TOKEN",
               "public_url": "SCRIBE_PUBLIC_URL", "default_voice": "SCRIBE_TWILIO_VOICE"}
    if env_map.get(field) and os.getenv(env_map[field]):
        return "env"
    return "default"


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "••••"
    return value[:3] + "••••" + value[-2:]


# ── Construction TwiML ───────────────────────────────────────────────────────
def _say(texte: str, code: str, voice: str) -> str:
    safe = _sax.escape(texte or "")
    return f'<Say language="{twilio_lang(code)}" voice="{_sax.escape(voice or "alice")}">{safe}</Say>'


def build_twiml_single(texte: str, code: str, voice: str, loop_pause: bool = True) -> str:
    """TwiML pour une ligne mono-langue : lit le message, répète."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]
    parts.append(_say(texte, code, voice))
    if loop_pause:
        parts.append('<Pause length="1"/>')
        parts.append(_say(texte, code, voice))
    parts.append("<Hangup/>")
    parts.append("</Response>")
    return "".join(parts)


def build_twiml_menu(langues: list, voice: str, action_url: str) -> str:
    """TwiML pré-menu SVI : « Pour le français tapez 1, for English press 2 »."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]
    parts.append(f'<Gather numDigits="1" timeout="6" action="{_sax.escape(action_url)}" method="POST">')
    for i, code in enumerate(langues, start=1):
        prompt = PROMPT_PRESS.get(code, PROMPT_PRESS["en"]).format(n=i)
        parts.append(_say(prompt, code, voice))
    parts.append("</Gather>")
    # Pas de saisie → langue principale (1).
    parts.append(f'<Redirect method="POST">{_sax.escape(action_url)}?Digits=1</Redirect>')
    parts.append("</Response>")
    return "".join(parts)


# ── REST Twilio (optionnel) ──────────────────────────────────────────────────
def _api_base(account_sid: str) -> str:
    return f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"


def test_credentials(db=None) -> dict:
    """Vérifie les identifiants Twilio (GET du compte). Retourne {ok, detail}."""
    cfg = get_config(db)
    if not (cfg["account_sid"] and cfg["auth_token"]):
        return {"ok": False, "mode": "dev", "detail": "Identifiants Twilio absents (mode DEV)."}
    try:
        import httpx
        url = _api_base(cfg["account_sid"]) + ".json"
        r = httpx.get(url, auth=(cfg["account_sid"], cfg["auth_token"]), timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "mode": "live",
                    "detail": f"Compte Twilio « {data.get('friendly_name', cfg['account_sid'])} » joignable."}
        return {"ok": False, "mode": "live",
                "detail": f"Twilio a répondu {r.status_code}. Vérifiez le SID et le token."}
    except Exception as e:
        return {"ok": False, "mode": "live", "detail": f"Échec d'appel Twilio : {e}"}


def set_number_webhook(numero: str, voice_url: str, db=None) -> dict:
    """Déclare l'URL du webhook voix sur un numéro Twilio (provisioning).

    Recherche l'IncomingPhoneNumber par numéro puis POST le champ VoiceUrl.
    Optionnel : en démo, on peut aussi le faire à la main dans la console Twilio.
    """
    cfg = get_config(db)
    if not (cfg["account_sid"] and cfg["auth_token"]):
        return {"ok": False, "detail": "Identifiants Twilio absents (mode DEV)."}
    if not numero:
        return {"ok": False, "detail": "Numéro absent."}
    try:
        import httpx
        base = _api_base(cfg["account_sid"])
        auth = (cfg["account_sid"], cfg["auth_token"])
        # Trouver le SID du numéro
        lr = httpx.get(base + "/IncomingPhoneNumbers.json",
                       params={"PhoneNumber": numero}, auth=auth, timeout=10.0)
        if lr.status_code != 200:
            return {"ok": False, "detail": f"Recherche du numéro : Twilio {lr.status_code}."}
        items = lr.json().get("incoming_phone_numbers", [])
        if not items:
            return {"ok": False, "detail": f"Numéro {numero} introuvable sur ce compte Twilio."}
        pn_sid = items[0]["sid"]
        ur = httpx.post(f"{base}/IncomingPhoneNumbers/{pn_sid}.json",
                        data={"VoiceUrl": voice_url, "VoiceMethod": "POST"},
                        auth=auth, timeout=10.0)
        if ur.status_code in (200, 201):
            return {"ok": True, "detail": f"Webhook voix déclaré sur {numero}."}
        return {"ok": False, "detail": f"Mise à jour du numéro : Twilio {ur.status_code}."}
    except Exception as e:
        return {"ok": False, "detail": f"Échec d'appel Twilio : {e}"}


def validate_signature(auth_token: str, url: str, params: dict, signature: str) -> bool:
    """Validation de la signature X-Twilio-Signature (sécurise le webhook)."""
    if not (auth_token and signature):
        return False
    try:
        import hmac
        s = url
        for k in sorted(params.keys()):
            s += k + str(params[k])
        mac = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1)
        digest = base64.b64encode(mac.digest()).decode("utf-8")
        return hmac.compare_digest(digest, signature)
    except Exception:
        return False
