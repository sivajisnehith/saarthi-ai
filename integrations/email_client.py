import asyncio
import smtplib
from email.message import EmailMessage
from pathlib import Path

from config.settings import (
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
)


class EmailClient:
    """Send customer ticket PDFs through a configured SMTP provider."""

    def _validate_configuration(self) -> None:
        if not all((SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL)):
            raise RuntimeError("SMTP email settings are not configured")

    def _send_ticket(self, destination: str, ticket_path: str) -> None:
        self._validate_configuration()

        pdf_path = Path(ticket_path)
        if not pdf_path.is_file():
            raise FileNotFoundError("The generated ticket PDF could not be found")

        message = EmailMessage()
        message["Subject"] = "Your Snehith Travels ticket"
        message["From"] = SMTP_FROM_EMAIL
        message["To"] = destination
        message.set_content(
            "Your Snehith Travels ticket is attached. "
            "Please carry a valid ID when boarding."
        )
        message.add_attachment(
            pdf_path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=pdf_path.name,
        )

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)

    async def send_ticket(self, destination: str, ticket_path: str) -> dict:
        await asyncio.to_thread(self._send_ticket, destination, ticket_path)
        return {
            "success": True,
            "destination": destination,
        }
