"""
plugins/repondeur/tts.py — SCRIBE
==================================
Synthèse vocale LOCALE (souveraine) : transforme le texte d'une annonce en
fichier audio MP3, prêt à téléverser sur le répondeur OVH (ou à pousser via API).

Chaîne : espeak-ng (voix locale, aucune clé, aucune donnée envoyée à l'extérieur)
→ WAV → MP3 via ffmpeg. Si ffmpeg est absent, on renvoie le WAV.

Qualité : espeak-ng est intelligible mais « robotique ». Pour une voix neurale
de meilleure qualité tout en restant souverain, installer Piper (détecté
automatiquement s'il est présent avec un modèle) — non requis pour fonctionner.

Prérequis VPS : `apt install espeak-ng ffmpeg`.
"""
import os
import shutil
import subprocess
import tempfile
import logging

logger = logging.getLogger("scribe.plugins.repondeur")

# Code SCRIBE (2 lettres) → voix espeak-ng
_ESPEAK_VOICE = {
    "fr": "fr", "en": "en-us", "de": "de", "es": "es", "it": "it", "nl": "nl",
    "pt": "pt", "pl": "pl", "sv": "sv", "da": "da", "fi": "fi", "el": "el",
    "cs": "cs", "ro": "ro", "ru": "ru", "no": "no", "hu": "hu", "bg": "bg",
    "hr": "hr", "sk": "sk", "sl": "sl", "lt": "lt", "lv": "lv", "et": "et",
    "ga": "ga", "mt": "mt", "ca": "ca",
}


def available() -> dict:
    return {
        "espeak": bool(shutil.which("espeak-ng") or shutil.which("espeak")),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "piper":  bool(shutil.which("piper")),
    }


def synthesize(text: str, lang: str = "fr", rate: int = 150):
    """Retourne (bytes_audio, mimetype) en cas de succès, sinon (None, detail)."""
    text = (text or "").strip()
    if not text:
        return None, "Texte vide."
    if len(text) > 8000:
        text = text[:8000]
    esp = shutil.which("espeak-ng") or shutil.which("espeak")
    ff  = shutil.which("ffmpeg")
    if not esp:
        return None, ("Moteur de synthèse vocale absent sur le serveur. "
                      "Installez-le : apt install espeak-ng ffmpeg")
    voice_base = _ESPEAK_VOICE.get((lang or "fr").lower()[:2], "fr")
    # Voix candidates : mbrola (plus naturelle) d'abord si installée, puis repli.
    if voice_base == "fr":
        candidates = ["mb-fr1", "fr"]
    elif voice_base == "en-us":
        candidates = ["mb-en1", "en-us"]
    else:
        candidates = [voice_base]
    tmpd = tempfile.mkdtemp(prefix="scribe_tts_")
    wav = os.path.join(tmpd, "a.wav")
    mp3 = os.path.join(tmpd, "a.mp3")
    try:
        made = False
        for voice in candidates:
            try:
                subprocess.run([esp, "-v", voice, "-s", str(rate), "-w", wav, text],
                               check=True, timeout=90, capture_output=True)
                if os.path.exists(wav) and os.path.getsize(wav) > 44:
                    made = True
                    break
            except Exception:
                continue
        if not made:
            return None, "Échec de la synthèse (voix indisponible)."
        if ff and os.path.exists(wav):
            subprocess.run([ff, "-y", "-i", wav, "-codec:a", "libmp3lame",
                            "-b:a", "96k", mp3],
                           check=True, timeout=90, capture_output=True)
            with open(mp3, "rb") as fh:
                return fh.read(), "audio/mpeg"
        with open(wav, "rb") as fh:
            return fh.read(), "audio/wav"
    except subprocess.TimeoutExpired:
        return None, "Synthèse trop longue (délai dépassé)."
    except Exception as e:
        return None, f"Échec de la synthèse : {e}"
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
