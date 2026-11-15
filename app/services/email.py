"""Email notification service supporting SMTP and in-memory test fakes."""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class EmailSenderProtocol(Protocol):
    """Protocol for sending outbound notification emails."""

    async def send_email(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> bool:
        """Send an email to a recipient with plain text and optional HTML content."""
        ...


class FakeEmailSender:
    """In-memory email sender for tests and development."""

    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    async def send_email(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> bool:
        """Record email in memory for assertions."""
        self.sent_emails.append(
            {
                "to": to,
                "subject": subject,
                "text_body": text_body,
                "html_body": html_body,
            }
        )
        return True

    def get_emails_for(self, to: str) -> list[dict[str, Any]]:
        """Retrieve sent emails filtered by recipient."""
        return [msg for msg in self.sent_emails if msg["to"].lower() == to.lower()]

    def clear(self) -> None:
        """Clear recorded emails."""
        self.sent_emails.clear()


class SMTPEmailSender:
    """Production SMTP email sender."""

    def __init__(self, settings: Settings) -> None:
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.from_email = settings.smtp_from_email
        self.use_tls = settings.smtp_use_tls

    def _send_sync(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> bool:
        """Synchronously dispatch email through SMTP."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = to

        part1 = MIMEText(text_body, "plain", "utf-8")
        msg.attach(part1)

        if html_body:
            part2 = MIMEText(html_body, "html", "utf-8")
            msg.attach(part2)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.sendmail(self.from_email, [to], msg.as_string())
            return True
        except Exception as exc:
            logger.error("Failed to send SMTP email to %s: %s", to, exc)
            return False

    async def send_email(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> bool:
        """Asynchronously dispatch email via thread pool."""
        return await asyncio.to_thread(self._send_sync, to, subject, text_body, html_body)
