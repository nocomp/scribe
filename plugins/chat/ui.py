"""plugins/chat/ui.py"""
import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

ui_router = APIRouter()

_HTML_PATH = os.path.join(os.path.dirname(__file__), "chat.html")

# v3.0.0-alpha19 — marker pour vérifier la version servie
# Incrémente à chaque build pour invalider les caches navigateur.
_BUILD_VERSION = "v3000h40f-uxfix"
_VERSION_MARKER = f"<!-- SCRIBE chat {_BUILD_VERSION} -->\n"

def _get_html() -> str:
    with open(_HTML_PATH, encoding="utf-8") as f:
        return _VERSION_MARKER + f.read()

# v3.0.0 — Headers no-cache pour éviter qu'un ancien chat.html buggé reste
# en cache navigateur après une mise à jour serveur.
_NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

@ui_router.get("/ui", response_class=HTMLResponse)
def chat_ui():
    return HTMLResponse(_get_html(), headers=_NO_CACHE)

@ui_router.get("/ui/popout", response_class=HTMLResponse)
def chat_ui_popout():
    return HTMLResponse(_get_html(), headers=_NO_CACHE)

@ui_router.get("/ui/version")
def chat_ui_version():
    """Diagnostic : retourne la version du chat.html servi.

    Permet de vérifier si l'instance a bien été redémarrée avec le bon code.
    Curl : http://localhost:8660/api/v1/chat/ui/version
    """
    has_sync_call = False
    has_chat_coll_disabled_ref = False
    try:
        with open(_HTML_PATH, encoding="utf-8") as f:
            content = f.read()
        # Si l'ancien code est encore là, ces tokens seront présents
        has_sync_call = "setInterval(chat_syncCollecteur, 3000)" in content
        # Une référence à _chatCollDisabled dans la fonction chat_syncCollecteur
        # indique qu'on a encore l'ancien bug
        has_chat_coll_disabled_ref = (
            "if (_chatCollDisabled) return;" in content
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, headers=_NO_CACHE)
    return JSONResponse({
        "build": _BUILD_VERSION,
        "expected": "v3000h40f-uxfix",
        "ok": (not has_sync_call) and (not has_chat_coll_disabled_ref),
        "old_setinterval_present": has_sync_call,
        "old_check_present": has_chat_coll_disabled_ref,
    }, headers=_NO_CACHE)
