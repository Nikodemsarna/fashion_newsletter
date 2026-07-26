"""Deliver the rendered edition by email (Resend API or SMTP)."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from .config import Settings

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


class DeliveryError(RuntimeError):
    """Raised when the configured provider fails to accept the message."""


def send_email(subject: str, html: str, text: str, settings: Settings) -> None:
    provider = settings.delivery_provider
    if provider == "resend":
        _send_via_resend(subject, html, text, settings)
    elif provider == "smtp":
        _send_via_smtp(subject, html, text, settings)
    else:
        raise DeliveryError(
            "No delivery provider configured. Set RESEND_API_KEY or SMTP_HOST."
        )


def _send_via_resend(subject: str, html: str, text: str, settings: Settings) -> None:
    payload = {
        "from": settings.sender,
        "to": [settings.recipient],
        "subject": subject,
        "html": html,
        "text": text,
    }
    try:
        resp = requests.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise DeliveryError(f"Resend request failed: {exc}") from exc
    if resp.status_code >= 300:
        raise DeliveryError(f"Resend rejected message ({resp.status_code}): {resp.text}")
    logger.info("Sent newsletter to %s via Resend.", settings.recipient)


def _send_via_smtp(subject: str, html: str, text: str, settings: Settings) -> None:
    if not settings.smtp_user or not settings.smtp_password:
        raise DeliveryError(
            "SMTP delivery requires both SMTP_USER and SMTP_PASSWORD. "
            "Set SMTP_USER to your full email address (e.g. you@gmail.com) and "
            "SMTP_PASSWORD to a Gmail App Password (16 chars, no spaces)."
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.sender
    message["To"] = settings.recipient
    message.attach(MIMEText(text, "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.sender, [settings.recipient], message.as_string())
    except (smtplib.SMTPException, OSError) as exc:
        raise DeliveryError(f"SMTP delivery failed: {exc}") from exc
    logger.info("Sent newsletter to %s via SMTP (%s).", settings.recipient, settings.smtp_host)
