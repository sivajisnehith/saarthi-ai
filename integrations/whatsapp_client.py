import logging
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import httpx

from config.settings import (
    META_WHATSAPP_ACCESS_TOKEN,
    META_WHATSAPP_PHONE_NUMBER_ID,
)

logger = logging.getLogger("saarthi.integrations.whatsapp")

META_WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("META_WHATSAPP_BUSINESS_ACCOUNT_ID", "4062573757379650")
META_WHATSAPP_TICKET_TEMPLATE_NAME = os.getenv("META_WHATSAPP_TICKET_TEMPLATE_NAME", "snehith_travels_ticket_pdf")


def normalize_whatsapp_phone(phone: str) -> str:
    """
    Normalizes a destination phone number for Meta WhatsApp Cloud API.
    Meta expects E.164 without leading '+':
    e.g. '918712145983' for Indian mobile numbers.
    Handles '8712145983', '+918712145983', '08712145983', 'whatsapp:+918712145983', etc.
    """
    if not phone or not str(phone).strip():
        raise ValueError("Phone number cannot be empty")

    cleaned = str(phone).strip()
    if cleaned.lower().startswith("whatsapp:"):
        cleaned = cleaned[9:].strip()

    # Remove formatting characters: spaces, dashes, parentheses, dots
    cleaned = re.sub(r"[\s\-\(\)\.]", "", cleaned)

    digits = cleaned
    if cleaned.startswith("+91"):
        digits = cleaned[3:]
    elif cleaned.startswith("+"):
        digits = cleaned[1:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        digits = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        digits = cleaned[1:]

    # Standard Indian 10-digit mobile
    if len(digits) == 10:
        if re.match(r"^[6-9]\d{9}$", digits):
            return f"91{digits}"
        raise ValueError(
            f"Invalid 10-digit mobile number '{phone}'. Indian mobile numbers must start with 6, 7, 8, or 9."
        )

    # If already 12 digits starting with 91[6-9]
    if re.match(r"^91[6-9]\d{9}$", digits):
        return digits

    # Other international numbers: 11-15 digits
    if digits.isdigit() and 11 <= len(digits) <= 15:
        return digits

    raise ValueError(f"Invalid phone number format: '{phone}'. Expected a valid 10-digit mobile number.")


class WhatsAppClient:
    """Send approved customer documents through the Meta WhatsApp Cloud API."""

    api_version = "v23.0"

    def __init__(self):
        self._template_status_cache: Dict[str, Tuple[bool, float]] = {}

    def _validate_configuration(self) -> None:
        if not META_WHATSAPP_ACCESS_TOKEN or not META_WHATSAPP_PHONE_NUMBER_ID:
            raise RuntimeError("Meta WhatsApp credentials are not configured")

    @property
    def _base_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {META_WHATSAPP_ACCESS_TOKEN}"}

    async def _is_template_approved(self, template_name: str, client: httpx.AsyncClient) -> bool:
        """Checks if a WhatsApp message template is approved on the WABA."""
        import time
        now = time.time()
        if template_name in self._template_status_cache:
            approved, cached_at = self._template_status_cache[template_name]
            if now - cached_at < 60:
                return approved

        waba_id = META_WHATSAPP_BUSINESS_ACCOUNT_ID
        if not waba_id:
            return False

        try:
            url = f"{self._base_url}/{waba_id}/message_templates?name={template_name}"
            resp = await client.get(url, headers=self._headers, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                templates = data.get("data", [])
                for t in templates:
                    if t.get("name") == template_name and t.get("status") == "APPROVED":
                        self._template_status_cache[template_name] = (True, now)
                        return True
            self._template_status_cache[template_name] = (False, now)
            return False
        except Exception as e:
            logger.warning("Error checking template status for %s: %s", template_name, e)
            return False

    async def upload_pdf(self, pdf_path: Path, client: httpx.AsyncClient) -> str:
        """Uploads a PDF to Meta Media API and returns media_id."""
        media_url = f"{self._base_url}/{META_WHATSAPP_PHONE_NUMBER_ID}/media"
        file_size = pdf_path.stat().st_size
        logger.info(
            "Uploading ticket PDF to Meta Media API | file=%s | size=%d bytes | url=%s",
            pdf_path.name,
            file_size,
            media_url,
        )

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

        if upload_response.status_code != 200:
            err_data = {}
            try:
                err_data = upload_response.json().get("error", {})
            except Exception:
                pass
            err_msg = err_data.get("message", upload_response.text[:200])
            err_code = err_data.get("code")
            fbtrace_id = err_data.get("fbtrace_id")
            logger.error(
                "Meta media upload failed | status=%s | code=%s | error=%s | fbtrace_id=%s",
                upload_response.status_code,
                err_code,
                err_msg,
                fbtrace_id,
            )
            raise RuntimeError(f"WhatsApp PDF upload failed (HTTP {upload_response.status_code}, code {err_code}): {err_msg}")

        media_id = upload_response.json().get("id")
        if not media_id:
            raise RuntimeError("Meta media upload response did not contain media ID")

        logger.info("PDF media uploaded successfully | media_id=%s", media_id)
        return media_id

    async def send_ticket(
        self,
        destination: str,
        ticket_path: str,
        customer_name: str = "Customer",
        booking_reference: str = "",
    ) -> dict:
        """Upload a PDF ticket and send it as a WhatsApp document message or approved template."""
        self._validate_configuration()

        # 1. Normalize destination phone number
        normalized_phone = normalize_whatsapp_phone(destination)
        logger.info(
            "Preparing WhatsApp ticket delivery | raw_destination=%s | normalized=%s",
            destination,
            normalized_phone,
        )

        # 2. Verify PDF file existence and readability
        pdf_path = Path(ticket_path)
        if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            logger.error("Ticket PDF file not found or empty: %s", ticket_path)
            raise FileNotFoundError(f"The generated ticket PDF could not be found or is empty at: {ticket_path}")

        message_url = f"{self._base_url}/{META_WHATSAPP_PHONE_NUMBER_ID}/messages"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 3. Upload PDF media
            media_id = await self.upload_pdf(pdf_path, client)

            # 4. Check if approved template with document header is available
            template_name = META_WHATSAPP_TICKET_TEMPLATE_NAME
            template_approved = await self._is_template_approved(template_name, client)

            sent_via = "direct_document"
            message_payload = None

            if template_approved:
                sent_via = "template"
                logger.info(
                    "Using approved WhatsApp template '%s' for ticket delivery to %s",
                    template_name,
                    normalized_phone,
                )
                message_payload = {
                    "messaging_product": "whatsapp",
                    "to": normalized_phone,
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {"code": "en"},
                        "components": [
                            {
                                "type": "header",
                                "parameters": [
                                    {
                                        "type": "document",
                                        "document": {
                                            "id": media_id,
                                            "filename": pdf_path.name,
                                        },
                                    }
                                ],
                            },
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": customer_name or "Customer"},
                                    {"type": "text", "text": booking_reference or "Confirmed Booking"},
                                ],
                            },
                        ],
                    },
                }
            else:
                logger.info(
                    "Sending ticket as direct document message to %s (template '%s' not active/approved)",
                    normalized_phone,
                    template_name,
                )
                caption = f"Your Snehith Travels e-ticket for booking #{booking_reference}" if booking_reference else "Your Snehith Travels digital e-ticket"
                message_payload = {
                    "messaging_product": "whatsapp",
                    "to": normalized_phone,
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "filename": pdf_path.name,
                        "caption": caption,
                    },
                }

            # 5. Dispatch message to Meta
            message_response = await client.post(
                message_url,
                headers={**self._headers, "Content-Type": "application/json"},
                json=message_payload,
            )

            # If template failed with translation / template error, try direct document fallback
            if message_response.status_code != 200 and sent_via == "template":
                logger.warning(
                    "Template delivery failed with HTTP %s: %s. Retrying with direct document message...",
                    message_response.status_code,
                    message_response.text[:200],
                )
                sent_via = "direct_document_fallback"
                caption = f"Your Snehith Travels e-ticket for booking #{booking_reference}" if booking_reference else "Your Snehith Travels digital e-ticket"
                fallback_payload = {
                    "messaging_product": "whatsapp",
                    "to": normalized_phone,
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "filename": pdf_path.name,
                        "caption": caption,
                    },
                }
                message_response = await client.post(
                    message_url,
                    headers={**self._headers, "Content-Type": "application/json"},
                    json=fallback_payload,
                )

            if message_response.status_code != 200:
                err_data = {}
                try:
                    err_data = message_response.json().get("error", {})
                except Exception:
                    pass
                err_msg = err_data.get("message", message_response.text[:200])
                err_code = err_data.get("code")
                err_details = err_data.get("error_data", {}).get("details", "")
                fbtrace_id = err_data.get("fbtrace_id")
                logger.error(
                    "Meta message dispatch failed | status=%s | code=%s | error=%s | details=%s | fbtrace_id=%s",
                    message_response.status_code,
                    err_code,
                    err_msg,
                    err_details,
                    fbtrace_id,
                )
                raise RuntimeError(
                    f"WhatsApp message delivery failed (HTTP {message_response.status_code}, code {err_code}): {err_msg} ({err_details})"
                )

            response_data = message_response.json()
            messages = response_data.get("messages", [])
            message_id = messages[0].get("id") if messages else None
            logger.info(
                "WhatsApp ticket delivery succeeded | method=%s | destination=%s | message_id=%s",
                sent_via,
                normalized_phone,
                message_id,
            )

            return {
                "success": True,
                "destination": destination,
                "normalized_destination": normalized_phone,
                "media_id": media_id,
                "message_id": message_id,
                "delivery_method": sent_via,
            }
