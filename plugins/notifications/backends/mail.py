"""
plugins/notifications/backends/mail.py — Backend SMTP standard.

Pas de dépendance externe : utilise smtplib/email de la stdlib Python.
Supporte STARTTLS (port 587 typique) et SMTPS (port 465).

Config attendue :
  {
    "smtp_host": "smtp.ch-nord.fr",
    "smtp_port": 587,
    "smtp_user": "scribe-alerts@ch-nord.fr",
    "smtp_pass": "...",
    "from_addr": "SCRIBE <scribe-alerts@ch-nord.fr>",
    "use_tls":   true,           # STARTTLS
    "use_ssl":   false,          # SMTPS direct
  }
"""
from __future__ import annotations
import asyncio
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders as _email_encoders
from email.utils import formatdate, make_msgid
from typing import Dict, Any

from plugins.notifications.backends.base import NotificationBackend, NotifPayload, NotifResult

logger = logging.getLogger("scribe.notifications.mail")


class MailBackend(NotificationBackend):
    kind = "mail"

    def is_configured(self) -> bool:
        c = self.config
        return bool(c.get("smtp_host")) and bool(c.get("from_addr"))

    def _build_message(self, payload: NotifPayload, to_addr: str, attachments=None) -> MIMEMultipart:
        emoji = payload.severity_emoji()
        subject = f"{emoji} SCRIBE — {payload.title}"[:200]

        # Corps texte brut (fallback pour clients sans HTML)
        text = (
            f"{payload.title}\n\n"
            f"{payload.body}\n\n"
            f"---\n"
            f"Niveau : {payload.urgency}/4\n"
            f"Type : {payload.event_type}\n"
        )
        url = payload.context.get("url")
        # h81 — Lien ABSOLU : si url est relatif (ex. /api/v1/...), on préfixe
        # base_url (sinon le client mail forge un lien cassé « http:/// »).
        _mbase = (payload.context.get("base_url") or "").rstrip("/")
        if url and url.startswith("/") and _mbase:
            url = _mbase + url
        if url:
            text += f"Consulter : {url}\n"

        # Corps HTML simple (sans dépendance, palette hospitalier)
        url_block = (
            f'<p style="margin:16px 0"><a href="{url}" '
            f'style="background:#003189;color:#fff;padding:10px 18px;'
            f'border-radius:4px;text-decoration:none;display:inline-block">'
            f'Consulter dans SCRIBE</a></p>' if url else ""
        )
        urgency_color = {1:"#64748b", 2:"#f59e0b", 3:"#ea580c", 4:"#dc2626"}.get(payload.urgency, "#64748b")
        urgency_label = {1:"Info", 2:"Vigilance", 3:"Alerte", 4:"CRITIQUE"}.get(payload.urgency, "Info")

        html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;color:#0f172a;background:#f8fafc;padding:20px">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0">
    <div style="background:{urgency_color};color:#fff;padding:14px 20px;font-size:13px;letter-spacing:1px;font-weight:700">
      {emoji} SCRIBE — {urgency_label}
    </div>
    <div style="padding:20px">
      <h2 style="margin:0 0 12px;font-size:18px;color:#0f172a">{_html_escape(payload.title)}</h2>
      <div style="color:#475569;line-height:1.5;font-size:14px;white-space:pre-wrap">{_html_escape(payload.body)}</div>
      {url_block}
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0">
      <div style="font-family:monospace;font-size:11px;color:#94a3b8">
        Événement : {payload.event_type} · Niveau {payload.urgency}/4
      </div>
    </div>
    <div style="background:#f1f5f9;padding:10px 20px;font-size:11px;color:#94a3b8;text-align:center">
      Cette notification a été émise automatiquement par SCRIBE Crisis OS.
    </div>
  </div>
</body></html>"""

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text, "plain", "utf-8"))
        alt.attach(MIMEText(html, "html",  "utf-8"))
        # h78 — Pièces jointes : on enveloppe l'alternative texte/HTML dans un
        # conteneur « mixed » et on y ajoute chaque fichier.
        if attachments:
            msg = MIMEMultipart("mixed")
            msg.attach(alt)
            for att in attachments:
                try:
                    fname, data, mime = att
                except Exception:
                    continue
                maintype, _, subtype = (mime or "application/octet-stream").partition("/")
                part = MIMEBase(maintype or "application", subtype or "octet-stream")
                part.set_payload(data)
                _email_encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=(fname or "fichier"))
                msg.attach(part)
        else:
            msg = alt
        msg["Subject"] = subject
        msg["From"]    = self.config.get("from_addr", "scribe@localhost")
        msg["To"]      = to_addr
        msg["Date"]    = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="scribe.local")
        if payload.urgency >= 3:
            msg["X-Priority"] = "1"
            msg["Importance"] = "high"
        return msg

    async def send(self, payload: NotifPayload, target: str, attachments=None) -> NotifResult:
        if not self.is_configured():
            return NotifResult(False, target, "Backend mail non configuré (smtp_host ou from_addr manquant)")
        try:
            msg = self._build_message(payload, target, attachments=attachments)
            # smtplib est bloquant : on le pousse dans un thread pour ne pas
            # bloquer l'event loop FastAPI.
            await asyncio.get_event_loop().run_in_executor(
                None, self._send_sync, msg, target
            )
            return NotifResult(True, target, backend_info={"message_id": msg["Message-ID"]})
        except Exception as e:
            logger.warning(f"Mail → {target} échec: {e}")
            return NotifResult(False, target, str(e))

    def _send_sync(self, msg, to_addr: str) -> None:
        c = self.config
        host = c["smtp_host"]
        port = int(c.get("smtp_port", 587))
        use_ssl = bool(c.get("use_ssl", False))
        use_tls = bool(c.get("use_tls", True)) and not use_ssl
        user = c.get("smtp_user")
        pwd  = c.get("smtp_pass")
        timeout = int(c.get("timeout", 20))

        if use_ssl:
            ctx = ssl.create_default_context()
            s = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx)
        else:
            s = smtplib.SMTP(host, port, timeout=timeout)
        try:
            s.ehlo()
            if use_tls:
                ctx = ssl.create_default_context()
                s.starttls(context=ctx)
                s.ehlo()
            if user and pwd:
                s.login(user, pwd)
            s.sendmail(msg["From"], [to_addr], msg.as_string())
        finally:
            try: s.quit()
            except Exception: pass


def _html_escape(s: str) -> str:
    return (str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))
