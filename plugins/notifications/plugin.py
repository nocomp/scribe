"""
plugins/notifications/plugin.py — SCRIBE v2.3.87

Plugin NOTIFICATIONS : multi-canal (Mail + Web Push + SMS) avec
mode sourdine, audio différencié par urgence, et abonnements par rôle.

Architecture :
- dispatcher.notify() : point d'entrée unique depuis n'importe où dans
  SCRIBE. Dispatche async vers tous les backends activés selon les
  règles de routage (urgency → canaux).
- Backends pluggables (base.NotificationBackend) : mail, webpush, sms.
- Modèles DB minimalistes : NotificationChannel, UserSubscription,
  SilenceMode, NotificationLog.
- UI admin : onglet NOTIFICATIONS dans le menu admin, avec test
  de chaque canal individuellement.

Cas d'usage principal :
- Un incident urgency=4 est créé → toute la cellule de crise reçoit
  un mail + une push navigateur + un SMS, avec son triangle hospitalier.
- Mode sourdine : silencieux sauf urgency=4 (les critiques passent
  toujours, c'est le contrat). Digest en fin de période.
"""

PLUGIN = {
    "id":           "notifications",
    "label":        "Notifications",
    "icon":         "🔔",
    "order":        90,
    "description":  "Notifications multi-canal (mail, push navigateur, SMS) pour les incidents critiques",
    "tab":          False,   # Pas un onglet principal, accessible via admin
    "admin_only":   True,
    "tab_id":       "tab-notifications",
    "api_prefix":   "/api/v1/notifications",
}

def register(app):
    from plugins.notifications.api import router
    app.include_router(router, prefix=PLUGIN["api_prefix"], tags=["NOTIFICATIONS"])
