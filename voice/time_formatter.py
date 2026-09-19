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

    Non-time strings (such as phone numbers, booking IDs, email addresses, URLs)
    are returned unchanged.
    """
    if not time_val or not isinstance(time_val, str):
        return ""

    cleaned = time_val.strip()

    # Match exact HH:MM or HH:MM:SS
    match = re.fullmatch(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])(?::[0-5][0-9])?$", cleaned)
    if not match:
        return time_val

    hour = int(match.group(1))
    minute = int(match.group(2))

    period = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12

    if minute == 0:
        return f"{hour_12} {period}"
    else:
        return f"{hour_12}:{minute:02d} {period}"


def format_spoken_times(text: str) -> str:
    """
    Finds 24-hour time patterns (HH:MM) in natural text and replaces them with
    conventional 12-hour spoken time format (e.g. "9 PM", "8:15 PM", "5:30 AM").

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
    # 3. 24-hour time HH:MM not attached to URL query params or paths
    pattern = (
        r"(https?://[^\s)]+|www\.[^\s)]+)|"
        r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})|"
        r"(?<![/\w?&=#@])\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b(?![/\w?&=#])"
    )

    def replace_match(match):
        # Group 1: URL -> preserve exactly as-is
        if match.group(1):
            return match.group(1)
        # Group 2: Email -> preserve exactly as-is
        if match.group(2):
            return match.group(2)
        # Group 3 & 4: HH:MM time
        hour_str = match.group(3)
        min_str = match.group(4)
        if hour_str is not None and min_str is not None:
            return format_time_for_speech(f"{hour_str}:{min_str}")
        return match.group(0)

    return re.sub(pattern, replace_match, text)
