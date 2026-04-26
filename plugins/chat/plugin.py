"""plugins/chat/plugin.py — SCRIBE Chat v1.0"""
from fastapi import FastAPI

MANIFEST = {
    "id":          "chat",
    "label":       "CHAT",
    "icon":        "💬",
    "order":       95,
    "description": "Messagerie instantanée intra et inter-GHT avec salons, mentions et pièces jointes",
    "api_prefix":  "/api/v1/chat",
    "tab_id":      "tab-chat",
    "has_tab":     True,
    "legacy":      False,
}

def register(app: FastAPI):
    from plugins.chat.models import Base
    from app.database import engine
    Base.metadata.create_all(bind=engine, checkfirst=True)

    from plugins.chat.routes import router
    from plugins.chat.ui     import ui_router
    from plugins.chat.sync   import sync_router

    app.include_router(router,      prefix="/api/v1/chat",      tags=["CHAT"])
    app.include_router(ui_router,   prefix="/api/v1/chat",      tags=["CHAT UI"])
    app.include_router(sync_router, prefix="/api/v1/chat/sync", tags=["CHAT SYNC"])
