"""
plugins/lignes/twilio_client.py — Helpers Twilio (sans SDK, httpx direct).

- Cartographie langue UE -> (voix Twilio, code langue) pour <Say>.
- Validation des identifiants (compte accessible ?).
- Appel de test : Twilio rappelle notre webhook TwiML public.

Aucun secret n'est journalisé. Tout échec est non bloquant et remonté en clair.
"""
import base64

# Langue UE -> (voix Twilio Polly, code langue BCP-47). Repli FR.
VOICE_MAP = {
    "fr": ("Polly.Lea",      "fr-FR"),
    "en": ("Polly.Amy",      "en-GB"),
    "de": ("Polly.Vicki",    "de-DE"),
    "es": ("Polly.Conchita", "es-ES"),
    "it": ("Polly.Carla",    "it-IT"),
    "pt": ("Polly.Ines",     "pt-PT"),
    "nl": ("Polly.Lotte",    "nl-NL"),
    "pl": ("Polly.Ewa",      "pl-PL"),
    "ro": ("Polly.Carmen",   "ro-RO"),
    "sv": ("Polly.Astrid",   "sv-SE"),
    "da": ("Polly.Naja",     "da-DK"),
}


def voice_for(langue: str, fallback_voice: str = "Polly.Lea"):
    v, lc = VOICE_MAP.get((langue or "fr")[:2].lower(), (fallback_voice, "fr-FR"))
    return v, lc


def _auth_header(sid: str, token: str) -> dict:
    raw = (sid + ":" + token).encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


async def validate_credentials(sid: str, token: str) -> tuple:
    """Retourne (ok: bool, message: str). Ne lève jamais."""
    if not sid or not token:
        return False, "Identifiants Twilio manquants."
    import httpx
    url = "https://api.twilio.com/2010-04-01/Accounts/%s.json" % sid
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_auth_header(sid, token))
        if r.status_code == 200:
            try:
                name = r.json().get("friendly_name", "")
            except Exception:
                name = ""
            return True, ("Compte Twilio accessible" + ((" : " + name) if name else ""))
        if r.status_code in (401, 403):
            return False, "Identifiants refuses par Twilio (401/403)."
        return False, "Reponse Twilio inattendue (HTTP %s)." % r.status_code
    except Exception as e:
        return False, "Erreur reseau vers Twilio : %s" % e


async def place_test_call(sid: str, token: str, from_number: str,
                          to_number: str, twiml_url: str) -> tuple:
    """Lance un appel : Twilio rappelle twiml_url pour lire l'annonce.
    Retourne (ok, message|sid_appel). Ne lève jamais."""
    if not (sid and token and from_number and to_number and twiml_url):
        return False, "Parametres incomplets (compte, numero emetteur, destinataire, URL)."
    import httpx
    url = "https://api.twilio.com/2010-04-01/Accounts/%s/Calls.json" % sid
    data = {"To": to_number, "From": from_number, "Url": twiml_url}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=_auth_header(sid, token), data=data)
        if r.status_code in (200, 201):
            try:
                csid = r.json().get("sid", "")
            except Exception:
                csid = ""
            return True, csid or "appel lance"
        detail = ""
        try:
            detail = r.json().get("message", "")
        except Exception:
            pass
        return False, "Echec appel Twilio (HTTP %s) %s" % (r.status_code, detail)
    except Exception as e:
        return False, "Erreur reseau vers Twilio : %s" % e
