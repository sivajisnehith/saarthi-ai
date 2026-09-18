from pathlib import Path

import httpx

from config.settings import (
    META_WHATSAPP_ACCESS_TOKEN,
    META_WHATSAPP_PHONE_NUMBER_ID,
)


class WhatsAppClient:
    """Send approved customer documents through the Meta WhatsApp Cloud API."""

    api_version = "v23.0"

    def _validate_configuration(self) -> None:
        if not META_WHATSAPP_ACCESS_TOKEN or not META_WHATSAPP_PHONE_NUMBER_ID:
            raise RuntimeError("Meta WhatsApp credentials are not configured")

    @property
    def _base_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {META_WHATSAPP_ACCESS_TOKEN}"}

    async def send_ticket(self, destination: str, ticket_path: str) -> dict:
        """Upload a PDF ticket and send it as a WhatsApp document message."""
        self._validate_configuration()

        pdf_path = Path(ticket_path)
        if not pdf_path.is_file():
            raise FileNotFoundError("The generated ticket PDF could not be found")

        media_url = f"{self._base_url}/{META_WHATSAPP_PHONE_NUMBER_ID}/media"
        message_url = f"{self._base_url}/{META_WHATSAPP_PHONE_NUMBER_ID}/messages"

        async with httpx.AsyncClient(timeout=30.0) as client:
            with pdf_path.open("rb") as ticket_file:
                upload_response = await client.post(
                    media_url,
                    headers=self._headers,
                    data={"messaging_product": "whatsapp"},
                    files={
                        "file": (
                            pdf_path.name,
                            ticket_file,
                            "application/pdf",
                        )
                    },
                )
            upload_response.raise_for_status()
            media_id = upload_response.json()["id"]

            message_response = await client.post(
                message_url,
                headers={**self._headers, "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "to": destination.lstrip("+"),
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "filename": pdf_path.name,
                    },
                },
            )
        message_response.raise_for_status()

        response_data = message_response.json()
        messages = response_data.get("messages", [])
        return {
            "success": True,
            "destination": destination,
            "message_id": messages[0].get("id") if messages else None,
        }
