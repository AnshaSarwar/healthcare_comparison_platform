"""Outbound transactional email for verification/reset/invite links.

No SMTP provider is set up in `infra/docker-compose.yml`, so the default
`email_backend="console"` just logs the message -- good enough for local dev, since the
token is visible in the API logs and can be copy-pasted into the confirm endpoint. Setting
`EMAIL_BACKEND=smtp` (plus the `smtp_*` settings) sends real mail via stdlib `smtplib`
against any standard SMTP provider without pulling in a vendor SDK.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeEmailMessage

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


def _send_smtp(message: EmailMessage) -> None:
    mime = MimeEmailMessage()
    mime["Subject"] = message.subject
    mime["From"] = settings.email_from
    mime["To"] = message.to
    mime.set_content(message.body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(mime)


async def send_email(message: EmailMessage) -> None:
    if settings.email_backend == "smtp":
        await asyncio.to_thread(_send_smtp, message)
        return
    # WARNING, not INFO: this repo has no app-wide logging config (see backend/main.py),
    # so Python's default "handler of last resort" only surfaces WARNING+ -- INFO here
    # would silently vanish, defeating the point of a backend whose whole job in local
    # dev is to make the token visible.
    logger.warning(
        "email(backend=console) to=%s subject=%s\n%s", message.to, message.subject, message.body
    )
