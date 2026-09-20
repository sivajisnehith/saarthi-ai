import re
from typing import Optional


def format_time_for_speech(time_val: str) -> str:
    """
    Converts a 24-hour time string (HH:MM) to natural 12-hour spoken format with AM/PM.

    Rules:
    - 24-hour HH:MM -> 12-hour format with AM/PM.
    - Omit minutes if 00 (e.g. "21:00" -> "9 PM", "09:00" -> "9 AM").
    - Preserve minutes if non-zero (e.g. "20:15" -> "8:15 PM", "05:30" -> "5:30 AM").
    - Strip leading zeroes from hour (e.g. "09" -> "9", "05" -> "5").
    - "00:00" -> "12 AM", "00:30" -> "12:30 AM".
    - "12:00" -> "12 PM", "12:15" -> "12:15 PM".
    - If existing AM/PM is passed (e.g. "7:15 AM", "6:00 PM"), format cleanly without duplicating.

    Non-time strings (such as phone numbers, booking IDs, email addresses, URLs)
    are returned unchanged.
    """
    if not time_val or not isinstance(time_val, str):
        return ""

    cleaned = time_val.strip()

    # Match exact HH:MM or HH:MM:SS with optional existing AM/PM
    match = re.fullmatch(
        r"^([01]?[0-9]|2[0-3]):([0-5][0-9])(?::[0-5][0-9])?(?:\s*(AM|PM|am|pm|a\.m\.|p\.m\.))?$",
        cleaned,
        re.IGNORECASE,
    )
    if not match:
        return time_val

    hour = int(match.group(1))
    minute = int(match.group(2))
    existing_period = match.group(3)

    if existing_period:
        clean_period = existing_period.upper().replace(".", "")
        hour_12 = hour % 12
        if hour_12 == 0:
            hour_12 = 12
        period = clean_period
    else:
        period = "AM" if hour < 12 else "PM"
        hour_12 = hour % 12
        if hour_12 == 0:
            hour_12 = 12

    if minute == 0:
        return f"{hour_12} {period}"
    else:
        return f"{hour_12}:{minute:02d} {period}"


def cleanup_duplicate_ampm(text: str) -> str:
    """
    Finds and collapses repeated AM/PM time suffixes (e.g. 'AM AM', 'PM PM', 'am AM', 'PM pm').
    Ensures that spoken voice responses never have stuttered/duplicate time indicators.
    """
    if not text:
        return ""
    # Matches "AM AM", "PM PM", "AM am", "a.m. AM", etc.
    return re.sub(
        r"\b(A\.M\.|P\.M\.|AM|PM|am|pm)(?:\s+(?:A\.M\.|P\.M\.|AM|PM|am|pm))+\b",
        lambda m: "PM" if "p" in m.group(0).lower() else "AM",
        text,
    )


def format_spoken_times(text: str) -> str:
    """
    Finds 24-hour and 12-hour time patterns in natural text and replaces them with
    conventional 12-hour spoken time format (e.g. "9 PM", "8:15 PM", "5:30 AM", "6 PM").
    Guarantees no duplicated AM/PM tokens.

    Targeted transformation that preserves:
    - URLs (e.g. https://example.com/test?time=21:00)
    - Email addresses (e.g. tejaithacha43@gmail.com)
    - Booking IDs (e.g. ST-MUYA2X)
    - Phone numbers (e.g. 8712145983)
    - Quantities & prices (e.g. 2 passengers, 999 rupees)
    """
    if not text:
        return ""

    # Pattern matches:
    # 1. URLs (http://... or https://... or www....)
    # 2. Email addresses (name@domain.com)
    # 3. Time HH:MM with optional existing AM/PM suffix: e.g. 7:15, 7:15 AM, 21:00, 05:30 AM
    pattern = (
        r"(https?://[^\s)]+|www\.[^\s)]+)|"
        r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})|"
        r"(?<![/\w?&=#@])\b([01]?[0-9]|2[0-3]):([0-5][0-9])(?:\s*(AM|PM|am|pm|a\.m\.|p\.m\.))?\b(?![/\w?&=#])"
    )

    def replace_match(match):
        # Group 1: URL -> preserve exactly as-is
        if match.group(1):
            return match.group(1)
        # Group 2: Email -> preserve exactly as-is
        if match.group(2):
            return match.group(2)
        # Group 3 & 4 & 5: Time HH:MM and optional AM/PM
        hour_str = match.group(3)
        min_str = match.group(4)
        period_str = match.group(5)
        if hour_str is not None and min_str is not None:
            time_expr = f"{hour_str}:{min_str} {period_str}" if period_str else f"{hour_str}:{min_str}"
            return format_time_for_speech(time_expr)
        return match.group(0)

    formatted = re.sub(pattern, replace_match, text)
    # Final pass: deduplicate any adjacent AM/PM suffixes
    return cleanup_duplicate_ampm(formatted)

