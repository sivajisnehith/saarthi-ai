"""
Saarthi AI Customer-Facing Progress Message and Stage Management Module.

Provides deterministic application-level progress notifications for slow tool operations
while preventing caller silence, duplicate announcements, and voice overlap.
"""

import logging
import re
from typing import Any, Dict, Optional, Set, Tuple

logger = logging.getLogger("saarthi.voice.progress")

# Mapping of tool names to (STAGE_ID, PROGRESS_MESSAGE_TEXT)
# ONLY meaningful, slow, customer-facing operations are mapped.
# Fast or trivial in-memory operations (recommend_seats, find_group_seats, hold_seats) are NOT mapped.
TOOL_PROGRESS_STAGES: Dict[str, Tuple[str, str]] = {
    "search_buses": (
        "STAGE_BUS_SEARCH",
        "Let me check the available buses. Just a moment.",
    ),
    "get_seats": (
        "STAGE_SEATS",
        "Let me check the available seats. Just a moment.",
    ),
    "create_booking": (
        "STAGE_BOOKING",
        "Sure, I'm booking that for you. Just a moment.",
    ),
    "create_payment": (
        "STAGE_PAYMENT_LINK",
        "I'm generating your payment link and sending it to WhatsApp. Just a moment.",
    ),
    "deliver_payment_link": (
        "STAGE_PAYMENT_LINK",
        "I'm generating your payment link and sending it to WhatsApp. Just a moment.",
    ),
    "get_payment_status": (
        "STAGE_PAYMENT_STATUS",
        "Let me check your payment status. Just a moment.",
    ),
    "generate_ticket": (
        "STAGE_TICKET_GEN",
        "I'm preparing your ticket. Just a moment.",
    ),
    "deliver_ticket_to_whatsapp": (
        "STAGE_WHATSAPP_TICKET",
        "Sure, I'm sending the ticket to WhatsApp. Just a moment.",
    ),
    "deliver_ticket_to_email": (
        "STAGE_EMAIL_TICKET",
        "Sure, I'm sending the ticket to your email. Just a moment.",
    ),
}

# Regex patterns for redundant progress prefixes in model outputs
REDUNDANT_PROGRESS_PATTERNS = [
    re.compile(
        r"^(?:sure,?\s*)?(?:let\s+me\s+check\s+the\s+available\s+buses\.?\s*(?:just\s+a\s+moment\.?)?)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sure,?\s*)?(?:let\s+me\s+check\s+the\s+available\s+seats\.?\s*(?:just\s+a\s+moment\.?)?)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sure,?\s*)?(?:i\'?m\s+booking\s+that\s+for\s+you\.?\s*(?:just\s+a\s+moment\.?)?)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sure,?\s*)?(?:i\'?m\s+generating\s+your\s+payment\s+link\s+and\s+sending\s+it\s+to\s+whatsapp\.?\s*(?:just\s+a\s+moment\.?)?)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sure,?\s*)?(?:let\s+me\s+check\s+your\s+payment\s+status\.?\s*(?:just\s+a\s+moment\.?)?)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sure,?\s*)?(?:i\'?m\s+preparing\s+your\s+ticket\.?\s*(?:just\s+a\s+moment\.?)?)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sure,?\s*)?(?:i\'?m\s+sending\s+the\s+ticket\s+to\s+whatsapp\.?\s*(?:just\s+a\s+moment\.?)?)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sure,?\s*)?(?:i\'?m\s+sending\s+the\s+ticket\s+to\s+your\s+email\.?\s*(?:just\s+a\s+moment\.?)?)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sure,?\s*)?(?:give\s+me\s+a\s+moment|please\s+(?:wait|hold|give\s+me\s+a\s+moment))\s*(?:while|as)?\s*(?:i|we)?\s*(?:check|confirm|generate|send|verify|book)[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:let\s+me\s+check\s+(?:the\s+)?(?:available\s+)?(?:buses|seats|payment)[^.!?]*[.!?]\s*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:i\'?m\s+(?:checking|generating|sending|preparing|booking)\s+[^.!?]*just\s+a\s+moment[.!?]\s*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:your\s+payment\s+is\s+confirmed[.,]\s*i\'?m\s+generating\s+your\s+ticket\s+now[.!?]\s*)",
        re.IGNORECASE,
    ),
]


class ProgressManager:
    """Tracks and coordinates progress messages per conversational turn."""

    def __init__(self):
        self.announced_stages: Set[str] = set()
        self.current_turn_id: int = 0

    def start_new_turn(self, turn_id: int):
        """Resets announced stages for a new customer speech turn."""
        self.announced_stages.clear()
        self.current_turn_id = turn_id

    def get_progress_for_tool(self, tool_name: str) -> Optional[Tuple[str, str]]:
        """
        Returns (stage_id, progress_message) if the tool requires an announcement
        and has NOT already been announced in the current turn.
        Returns None for trivial operations or if already announced.
        """
        if not tool_name or tool_name not in TOOL_PROGRESS_STAGES:
            return None

        stage_id, text = TOOL_PROGRESS_STAGES[tool_name]
        if stage_id in self.announced_stages:
            logger.debug(
                "Skipping duplicate progress message for stage %s (tool=%s)",
                stage_id,
                tool_name,
            )
            return None

        return stage_id, text

    def mark_stage_announced(self, stage_id: str):
        """Marks a stage as announced in this turn to prevent duplication."""
        self.announced_stages.add(stage_id)


def strip_redundant_progress_prefix(final_text: str, announced_stages: Set[str]) -> str:
    """
    If a progress message was already played to the customer before the tool executed,
    strips redundant conversational progress phrases from the final model output
    so that the customer doesn't hear the exact same progress announcement twice.
    """
    if not final_text or not announced_stages:
        return final_text

    cleaned = final_text.strip()
    for pattern in REDUNDANT_PROGRESS_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            # Strip the matched redundant progress prefix
            remainder = cleaned[match.end():].strip()
            # Only strip if there is still meaningful content left
            if remainder:
                cleaned = remainder

    return cleaned


_active_progress_callback: Optional[Any] = None


def set_active_progress_callback(callback: Optional[Any]):
    """Registers an active progress trigger callback for the current live session."""
    global _active_progress_callback
    _active_progress_callback = callback


async def notify_tool_execution_start(tool_name: str):
    """
    Called directly by tools at entry point to guarantee deterministic progress
    speech happens in the real live execution path.
    """
    if _active_progress_callback:
        try:
            import inspect
            if inspect.iscoroutinefunction(_active_progress_callback):
                await _active_progress_callback(tool_name)
            else:
                _active_progress_callback(tool_name)
        except Exception as ex:
            logger.error("Error executing progress callback for tool %s: %s", tool_name, ex)

