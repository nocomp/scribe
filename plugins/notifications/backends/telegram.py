# plugins/notifications/backends/telegram.py
# h148 — Canal Telegram retiré de SCRIBE (non conforme au cadre OSE santé français).
# Fichier conservé vide pour compatibilité ascendante des anciens abonnements
# stockés en base (kind='telegram'). Les envois retournent toujours une erreur.

from .base import BaseBackend

class TelegramBackend(BaseBackend):
    kind = "telegram"
    available = False   # signale au dispatcher que ce canal est désactivé

    async def send(self, *args, **kwargs):
        return {"ok": False, "error": "Canal Telegram retiré — non disponible dans cette version de SCRIBE."}

    async def test(self, *args, **kwargs):
        return {"ok": False, "error": "Canal Telegram retiré."}
