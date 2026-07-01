"""
plugins/repondeur/stt.py — SCRIBE
==================================
Transcription vocale LOCALE (souveraine) des messages du répondeur.

Principe : l'audio du message vocal est récupéré depuis OVH, puis transcrit
ICI, sur le serveur SCRIBE — aucune dépendance à la transcription OVH, aucune
donnée envoyée à un tiers. On ne conserve pas l'audio : il est transcrit dans un
fichier temporaire supprimé aussitôt (minimisation RGPD).

Moteurs supportés (le premier disponible est utilisé) :
  1. faster-whisper  (pip install faster-whisper)  — meilleure qualité FR, CPU/int8
  2. openai-whisper  (pip install openai-whisper)   — binaire `whisper` ou module
  3. vosk            (pip install vosk + modèle FR)  — léger, hors-ligne

Prérequis VPS (une fois) — au choix :
  pip install faster-whisper            # recommandé
  # ou : pip install vosk  + modèle FR dans SCRIBE_VOSK_MODEL

Le modèle faster-whisper (défaut « base ») se télécharge une fois au premier
usage ; taille via SCRIBE_WHISPER_MODEL (tiny/base/small).
"""
import os
import shutil
import subprocess
import tempfile
import logging

logger = logging.getLogger("scribe.plugins.repondeur")

_WHISPER_MODEL = None       # cache faster-whisper
_VOSK_MODEL = None          # cache vosk


def available() -> dict:
    out = {"faster_whisper": False, "whisper": False, "vosk": False, "ffmpeg": bool(shutil.which("ffmpeg"))}
    try:
        import faster_whisper  # noqa
        out["faster_whisper"] = True
    except Exception:
        pass
    if shutil.which("whisper"):
        out["whisper"] = True
    else:
        try:
            import whisper  # noqa
            out["whisper"] = True
        except Exception:
            pass
    try:
        import vosk  # noqa
        if os.environ.get("SCRIBE_VOSK_MODEL"):
            out["vosk"] = True
    except Exception:
        pass
    return out


def _to_wav16k(audio_bytes: bytes, suffix: str = ".mp3"):
    """Écrit l'audio dans un WAV 16 kHz mono (format attendu par les moteurs STT).
    Retourne le chemin du WAV, ou None. L'appelant nettoie le dossier temporaire."""
    ff = shutil.which("ffmpeg")
    tmpd = tempfile.mkdtemp(prefix="scribe_stt_")
    src = os.path.join(tmpd, "in" + suffix)
    wav = os.path.join(tmpd, "out.wav")
    with open(src, "wb") as fh:
        fh.write(audio_bytes)
    if not ff:
        # pas de ffmpeg : on tente l'audio brut (faster-whisper sait décoder seul)
        return src, tmpd
    try:
        subprocess.run([ff, "-y", "-i", src, "-ar", "16000", "-ac", "1", wav],
                       check=True, timeout=120, capture_output=True)
        return wav, tmpd
    except Exception:
        return src, tmpd


def _try_faster_whisper(path, lang):
    global _WHISPER_MODEL
    from faster_whisper import WhisperModel
    if _WHISPER_MODEL is None:
        size = os.environ.get("SCRIBE_WHISPER_MODEL", "base")
        _WHISPER_MODEL = WhisperModel(size, device="cpu", compute_type="int8")
    segments, _info = _WHISPER_MODEL.transcribe(path, language=(lang or "fr"), vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def _try_whisper_cli(path, lang):
    exe = shutil.which("whisper")
    if not exe:
        return None
    outd = os.path.dirname(path)
    subprocess.run([exe, path, "--language", (lang or "fr"), "--model", "base",
                    "--output_format", "txt", "--output_dir", outd, "--fp16", "False"],
                   check=True, timeout=300, capture_output=True)
    txt = os.path.splitext(path)[0] + ".txt"
    if os.path.exists(txt):
        return open(txt, encoding="utf-8").read().strip()
    return None


def _try_vosk(path, lang):
    global _VOSK_MODEL
    model_dir = os.environ.get("SCRIBE_VOSK_MODEL")
    if not model_dir or not os.path.isdir(model_dir):
        return None
    import wave, json as _json
    from vosk import Model, KaldiRecognizer
    if _VOSK_MODEL is None:
        _VOSK_MODEL = Model(model_dir)
    wf = wave.open(path, "rb")
    rec = KaldiRecognizer(_VOSK_MODEL, wf.getframerate())
    rec.SetWords(False)
    out = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            out.append(_json.loads(rec.Result()).get("text", ""))
    out.append(_json.loads(rec.FinalResult()).get("text", ""))
    return " ".join(t for t in out if t).strip()


def transcribe(audio_bytes: bytes, lang: str = "fr", suffix: str = ".mp3"):
    """Transcrit l'audio localement. Retourne (texte, None) ou (None, detail)."""
    if not audio_bytes:
        return None, "Audio vide."
    path, tmpd = _to_wav16k(audio_bytes, suffix=suffix)
    try:
        # 1) faster-whisper
        try:
            import faster_whisper  # noqa
            txt = _try_faster_whisper(path, lang)
            if txt is not None:
                return (txt or "(silence / inaudible)"), None
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"faster-whisper: {e}")
        # 2) whisper (CLI ou module)
        try:
            txt = _try_whisper_cli(path, lang)
            if txt is not None:
                return (txt or "(silence / inaudible)"), None
        except Exception as e:
            logger.warning(f"whisper CLI: {e}")
        # 3) vosk
        try:
            txt = _try_vosk(path, lang)
            if txt is not None:
                return (txt or "(silence / inaudible)"), None
        except Exception as e:
            logger.warning(f"vosk: {e}")
        return None, ("Aucun moteur de transcription installé sur le serveur. "
                      "Installez-en un : pip install faster-whisper  (recommandé).")
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
