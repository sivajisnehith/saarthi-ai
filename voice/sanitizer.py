"""
Saarthi AI Response Sanitization and Safety Module.

Provides robust filtering for telephone voice responses:
1. Internal reasoning/execution narration filtering (sentence-by-sentence).
2. Unrelated foreign script contamination removal (e.g. CJK/Cyrillic in Telugu/English calls).
3. Legitimate entity preservation (places, numbers, emails, phone numbers, booking refs).
4. Sentence-aware conciseness enforcement (~5-15s conversational target).
5. Currency and spoken time formatting.
6. Target language code detection for Sarvam TTS (te-IN, hi-IN, en-IN).
"""

import re
from typing import Any, List, Optional


# XML-style and scratchpad tags emitted during model reasoning
INTERNAL_TAGS = [
    "reasoning",
    "thought",
    "think",
    "analysis",
    "internal",
    "tool",
    "tool_call",
    "tool_response",
    "tool_selection",
    "scratchpad",
    "planning",
    "plan",
    "reflection",
    "decision",
    "system",
    "instruction",
]

# Exact phrases or fragments representing internal execution state
INTERNAL_PHRASES = [
    r"waiting for (?:your )?confirmation",
    r"waiting for user confirmation",
    r"waiting for the user to confirm",
    r"internal decision making:?",
    r"tool-selection reasoning:?",
    r"chain-of-thought:?",
    r"internal planning:?",
    r"internal status narration:?",
]

# Sentence-level regex patterns that identify internal narration or developer self-talk
INTERNAL_SENTENCE_PATTERNS = [
    # "Now I/we need to...", "I need to ask...", "We need to..."
    re.compile(r"^(?:now\s+)?(?:i|we)\s+need\s+to\b", re.IGNORECASE),
    # "Proceed to...", "Proceeding to..."
    re.compile(r"^(?:proceed|proceeding)\s+to\b", re.IGNORECASE),
    # "Next I/we should...", "I/we should..."
    re.compile(r"^(?:next\s+)?(?:i|we)\s+should\b", re.IGNORECASE),
    # "Now I will call...", "I will now invoke...", "We will now call..."
    re.compile(
        r"^(?:now\s+)?(?:i|we)\s+will\s+(?:now\s+)?(?:call|invoke|execute|fetch|check|query|run|trigger|proceed)\b",
        re.IGNORECASE,
    ),
    # "Let me call/invoke/query/execute ..."
    re.compile(
        r"^let\s+me\s+(?:call|invoke|execute|query|run)\b",
        re.IGNORECASE,
    ),
    # Any exact tool name mentioned in sentence
    re.compile(
        r"\b(?:search_buses|get_seats|recommend_seats|find_group_seats|hold_seats|create_booking|create_payment|get_payment_status|get_ticket|generate_ticket|deliver_ticket_to_whatsapp|deliver_ticket_to_email|deliver_payment_link)\b",
        re.IGNORECASE,
    ),
    # "Let's check..." / "Let us check..." (Internal reasoning, distinct from customer-facing "Let me check ... for you")
    re.compile(r"^let\'?s\s+check\b", re.IGNORECASE),
    re.compile(r"^let\s+us\s+check\b", re.IGNORECASE),
    # "I/we have invoked/called/executed..."
    re.compile(
        r"^(?:i|we)\s+have\s+(?:invoked|called|executed|queried|run)\b",
        re.IGNORECASE,
    ),
    # "The tool returned...", "The API returned...", "The database shows...", etc.
    re.compile(
        r"\b(?:the\s+)?(?:tool|api|function|system|database)\s+(?:returned|shows|showed|has\s+shown|responded|indicated|confirmed|failed|executed|was\s+invoked)\b",
        re.IGNORECASE,
    ),
    # Specific tool/system references
    re.compile(r"\b(?:the\s+)?hold\s+token\b", re.IGNORECASE),
    re.compile(
        r"\b(?:the\s+)?booking\s+id\s+(?:is|has\s+been|was)\s+(?:recorded|stored|created|generated|saved|in)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:recorded|stored|saved)\s+in\s+the\s+database\b", re.IGNORECASE),
    re.compile(r"\b(?:the\s+)?function\s+call\b", re.IGNORECASE),
    re.compile(r"\b(?:the\s+)?tool\s+call\b", re.IGNORECASE),
    re.compile(r"\b(?:waiting\s+for\s+(?:user|customer|your)\s+confirmation)\b", re.IGNORECASE),
    re.compile(r"\b(?:internal\s+(?:reasoning|decision|planning|workflow))\b", re.IGNORECASE),
    re.compile(r"^\s*(?:action|action\s+input|observation|thought)\s*:\s*", re.IGNORECASE),
]

# Patterns for detecting completely unrelated foreign scripts (CJK, Korean, Cyrillic, Arabic, Thai)
# Indian languages (Telugu, Hindi/Devanagari, Tamil, Kannada, etc.) and Latin/English are ALLOWED.
UNRELATED_SCRIPT_RE = re.compile(
    r"[\u4e00-\u9fff"   # CJK Unified Ideographs
    r"\u3400-\u4dbf"   # CJK Unified Ideographs Extension A
    r"\uf900-\ufaff"   # CJK Compatibility Ideographs
    r"\u3000-\u303f"   # CJK Symbols and Punctuation (e.g. 。 、 「 」)
    r"\u3040-\u30ff"   # Japanese Hiragana and Katakana
    r"\uac00-\ud7af"   # Korean Hangul Syllables
    r"\u1100-\u11ff"   # Korean Hangul Jamo
    r"\u0400-\u04ff"   # Cyrillic
    r"\u0600-\u06ff"   # Arabic
    r"\u0e00-\u0e7f"   # Thai
    r"]"
)


def is_internal_sentence(sentence: str) -> bool:
    """
    Determines if a sentence is internal execution narration or developer self-talk.
    Carefully distinguishes between:
    - Customer-facing: "Let me check the available buses for you." -> False
    - Internal narration: "Now I need to check the available buses." -> True
    - Internal narration: "Let me call the search_buses tool." -> True
    - Customer-facing: "Sure, give me a moment while I check the available seats." -> False
    """
    clean_s = sentence.strip()
    if not clean_s:
        return False

    # Check for raw JSON structures in sentence
    if clean_s.startswith("{") and clean_s.endswith("}"):
        return True
    if clean_s.startswith("[") and clean_s.endswith("]"):
        return True
    if re.search(r'["\'](?:tool|action|booking_id|hold_token)["\']\s*:', clean_s):
        return True

    # Check against all internal sentence patterns
    for pattern in INTERNAL_SENTENCE_PATTERNS:
        if pattern.search(clean_s):
            return True

    return False


def sanitize_agent_text(text: str) -> str:
    """
    Defensively strips:
    1. Paired and unclosed XML reasoning tags (<reasoning>...</reasoning>, <think>, etc.)
    2. Markdown code blocks and tool payloads.
    3. Internal status phrases.
    4. Sentence-level internal workflow narration while preserving legitimate customer-facing sentences.
    """
    if not text:
        return ""

    # 1. Strip paired internal tags
    for tag in INTERNAL_TAGS:
        pattern = rf"<{tag}\b[^>]*>.*?</{tag}>"
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    # 2. Strip unclosed opening tags at beginning of text
    for tag in INTERNAL_TAGS:
        pattern = rf"^\s*<{tag}\b[^>]*>.*?(?=\n\n|\Z)"
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    # 3. Strip trailing unclosed opening tags
    for tag in INTERNAL_TAGS:
        pattern = rf"<{tag}\b[^>]*>.*$"
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    # 4. Strip stray closing tags
    for tag in INTERNAL_TAGS:
        text = re.sub(rf"</{tag}>", "", text, flags=re.IGNORECASE)

    # 5. Strip markdown code blocks of tool calls / json payloads
    text = re.sub(
        r"```(?:json|tool|tool_call)?\s*[\{\[].*?[\}\]]\s*```",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 6. Strip internal status phrases
    for phrase in INTERNAL_PHRASES:
        text = re.sub(rf"(?i)\b{phrase}\b[.:]?", "", text)

    # 7. Sentence-by-sentence internal narration filtering
    # Split text into sentences preserving separators
    lines = text.split("\n")
    kept_lines = []
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Split line into sentences
        sentence_splits = re.split(r"(?<=[.!?])\s+", line_clean)
        kept_sentences = []
        for s in sentence_splits:
            if not is_internal_sentence(s):
                kept_sentences.append(s.strip())

        if kept_sentences:
            kept_lines.append(" ".join(kept_sentences))

    text = " ".join(kept_lines)

    # 8. Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text).strip()
    return text


def sanitize_multilingual_contamination(text: str) -> str:
    """
    Removes accidental foreign script contamination (e.g. Chinese characters slipping
    into Telugu or English responses) while strictly preserving:
    - Telugu ([\u0c00-\u0c7f])
    - Hindi / Devanagari ([\u0900-\u097f])
    - Other intended Indian scripts (Tamil, Kannada, etc.)
    - English (a-zA-Z)
    - Numbers, times, dates, and currency (₹, $)
    - Place names, bus names, email addresses, phone numbers, booking references.
    """
    if not text:
        return ""

    if not UNRELATED_SCRIPT_RE.search(text):
        return text

    # Split by sentence or punctuation boundaries to isolate contaminated parts
    sentences = re.split(r"(?<=[.!?,;:\u3002])\s+", text)
    clean_sentences = []

    for s in sentences:
        s_stripped = s.strip()
        if not s_stripped:
            continue

        # If this segment contains foreign script characters, remove those characters
        if UNRELATED_SCRIPT_RE.search(s_stripped):
            cleaned_s = UNRELATED_SCRIPT_RE.sub("", s_stripped).strip()
            # If after stripping the segment has valid text left, keep it
            if cleaned_s and any(c.isalnum() for c in cleaned_s):
                clean_sentences.append(cleaned_s)
        else:
            clean_sentences.append(s_stripped)

    result = " ".join(clean_sentences)
    # Clean up double punctuation or awkward whitespace
    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r"([.!?])\s*([.!?])", r"\1", result).strip()
    return result


def detect_response_language(text: str) -> str:
    """
    Detects the primary Indic/English language of the response for Sarvam TTS.
    Returns Sarvam language code:
    - 'te-IN' for Telugu
    - 'hi-IN' for Hindi
    - 'ta-IN' for Tamil
    - 'kn-IN' for Kannada
    - 'en-IN' for English (default)
    """
    if not text:
        return "en-IN"

    if re.search(r"[\u0c00-\u0c7f]", text):
        return "te-IN"
    if re.search(r"[\u0900-\u097f]", text):
        return "hi-IN"
    if re.search(r"[\u0b80-\u0bff]", text):
        return "ta-IN"
    if re.search(r"[\u0c80-\u0cff]", text):
        return "kn-IN"

    return "en-IN"


def strip_instruction_leak(text: str) -> str:
    """
    Strips internal narration / instruction leaks such as:
    - 'Thus ask: "Please tell me the name..."Please tell me the name...'
    - 'Now ask: "..."'
    - 'Proceed to ask: ...'
    - 'Therefore ask: ...'
    - 'So ask: ...'
    - 'Ask: ...'
    And cleans up quotation duplication.
    """
    if not text:
        return ""
    cleaned = text.strip()

    # Pattern for instruction prefixes
    prefix_pattern = r"(?:^|\n)\s*(?:(?:thus|now|next|so|therefore|then|proceed\s+to)\s+)?(?:ask|inquire|tell\s+the\s+customer|request)\s*:\s*"
    cleaned = re.sub(prefix_pattern, " ", cleaned, flags=re.IGNORECASE).strip()

    # Handle quoted duplication: "X"X or "X" X or "X" followed by partial or complete X
    quoted_dup = re.match(r'^"([^"]+)"\s*(.*)$', cleaned, re.DOTALL)
    if quoted_dup:
        quoted_part = quoted_dup.group(1).strip()
        rest = quoted_dup.group(2).strip()
        if not rest or rest == quoted_part or rest.startswith(quoted_part):
            cleaned = quoted_part
        elif quoted_part.startswith(rest):
            cleaned = quoted_part
        else:
            cleaned = f"{quoted_part} {rest}".strip()

    # Strip enclosing quotes if any
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) > 1:
        cleaned = cleaned[1:-1].strip()

    return cleaned


def remove_internal_ids_from_voice(text: str) -> str:
    """
    Removes database IDs and internal identifiers that should not be spoken over the phone:
    - '(bus 2)', '(bus ID 2)', '(bus #2)', '(bus: 2)'
    - '(booking 47)', '(booking ID 47)', '(booking ID: 47)'
    - 'booking ID 47' -> 'your booking'
    - '(the) bus ID 2' -> 'the bus'
    - 'on bus 2' -> 'on the bus'
    - 'bus 2 is...' -> 'The bus is...'
    Preserves phone numbers, ticket reference codes (ST-...), seat numbers, dates, and prices.
    """
    if not text:
        return ""
    cleaned = text
    # 1. Remove parenthetical (bus 2), (bus ID 2), (bus #2), (bus: 2)
    cleaned = re.sub(r"\s*\(\s*bus(?:\s+id)?\s*[:#]?\s*\d+\s*\)", "", cleaned, flags=re.IGNORECASE)
    # 2. Remove parenthetical (booking 47), (booking ID 47), (booking ID: 47)
    cleaned = re.sub(r"\s*\(\s*booking(?:\s+id)?\s*[:#]?\s*\d+\s*\)", "", cleaned, flags=re.IGNORECASE)
    # 3. Clean "booking ID 47" -> "your booking"
    cleaned = re.sub(r"\b(?:your\s+)?booking\s+id\s*[:#]?\s*\d+\b", "your booking", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\byour\s+your\b", "your", cleaned, flags=re.IGNORECASE)
    # 4. Clean "(the) bus ID 2" or "bus #2"
    cleaned = re.sub(r"\b(?:the\s+)?bus\s+id\s*[:#]?\s*\d+\b", "the bus", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:the\s+)?bus\s*#\d+\b", "the bus", cleaned, flags=re.IGNORECASE)
    # 5. Clean "on bus 2" -> "on the bus", "in bus 2" -> "in the bus"
    cleaned = re.sub(r"\b(on|for|in|at)\s+bus\s+\d+\b", r"\1 the bus", cleaned, flags=re.IGNORECASE)
    # 6. Clean "bus 2 is/leaves/departs/arrives..." -> "the bus is..."
    cleaned = re.sub(r"\bbus\s+\d+\s+(is|leaves|departs|arrives)\b", r"the bus \1", cleaned, flags=re.IGNORECASE)
    # 7. Normalize double words
    cleaned = re.sub(r"\bthe\s+the\b", "the", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 8. Fix sentence capitalization if started with "your" or "the"
    if cleaned.startswith("your booking"):
        cleaned = "Your booking" + cleaned[len("your booking"):]
    elif cleaned.startswith("the bus"):
        cleaned = "The bus" + cleaned[len("the bus"):]
    return cleaned


def strip_times_from_boarding_points(text: str) -> str:
    """
    Strips arrival and departure times from lists of boarding / dropping points:
    'Boarding points are KPHB (6:45 AM), Ameerpet (7:15 AM), and Lakdikapul (7:45 AM).'
    -> 'Boarding points are KPHB, Ameerpet, and Lakdikapul.'
    """
    if not text:
        return ""
    cleaned = text
    # Match parenthetical times like (6:45 AM), (06:45), (7 PM)
    cleaned = re.sub(r"\s*\(\s*\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?\s*\)", "", cleaned)
    # In context of boarding/dropping points, also strip "at 6:45 AM" if present
    if re.search(r"\b(?:boarding|dropping|pickup)\s+points?\b", cleaned, re.IGNORECASE):
        cleaned = re.sub(r"\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def enforce_concise_voice_response(text: str, max_words: int = 28) -> str:
    """
    Sentence-aware length safeguard for voice responses.
    Ensures spoken responses stay within conversational duration (~3-8s),
    preventing lengthy monologues while never truncating mid-sentence,
    mid-word, mid-email, or mid-URL.
    """
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()

    if len(words) <= max_words:
        return text

    # Split into complete sentences
    sentence_pattern = r"(?<=[.!?])\s+"
    sentences = [s.strip() for s in re.split(sentence_pattern, text) if s.strip()]

    if len(sentences) <= 2 and len(words) <= max_words + 15:
        return text

    # Always keep first sentence (the primary statement)
    selected = [sentences[0]]

    # Check if final sentence is a question (action prompt for customer)
    last_sentence = sentences[-1]
    last_is_question = last_sentence.endswith("?")

    if last_is_question and len(sentences) > 1:
        if len(sentences) > 2:
            candidate = f"{sentences[0]} {sentences[1]} {last_sentence}"
            # If candidate fits or if sentence 0 is a short intro (< 7 words) and candidate is <= max_words + 8
            if len(candidate.split()) <= max_words or (len(sentences[0].split()) <= 6 and len(candidate.split()) <= max_words + 8):
                selected.append(sentences[1])
        selected.append(last_sentence)
    else:
        for s in sentences[1:]:
            candidate = " ".join(selected + [s])
            if len(candidate.split()) <= max_words:
                selected.append(s)
            else:
                break

    result = " ".join(selected).strip()
    return result if result else text


# Bus name shortening mappings for natural phone speech
KNOWN_BUS_NAME_REPLACEMENTS = [
    (re.compile(r"\bKaveri(?:\s+Twilight)?(?:\s+AC)?\s+Sleeper\b", re.IGNORECASE), "Kaveri sleeper"),
    (re.compile(r"\bKrishnaveni(?:\s+Morning)?(?:\s+Superfast)?\b", re.IGNORECASE), "Krishnaveni"),
    (re.compile(r"\bZingbus(?:\s+Volvo)?(?:\s+9600)?(?:\s+Multi-?Axle)?\s+Sleeper\b", re.IGNORECASE), "Zingbus sleeper"),
    (re.compile(r"\bSnehith\s+Express(?:\s+AC)?(?:\s+Seater)?\b", re.IGNORECASE), "Snehith Express"),
    (re.compile(r"\bSnehith\s+Gold\s+Class(?:\s+Volvo)?(?:\s+9600)?\b", re.IGNORECASE), "Snehith Gold Class"),
    (re.compile(r"\bVRL(?:\s+I-?Shift)?(?:\s+Multi-?Axle)?(?:\s+AC)?\s+Sleeper\b", re.IGNORECASE), "VRL sleeper"),
    (re.compile(r"\bOrange(?:\s+Scania)?(?:\s+Multi-?Axle)?(?:\s+AC)?\s+Sleeper\b", re.IGNORECASE), "Orange sleeper"),
    (re.compile(r"\bDeccan\s+Royal(?:\s+AC)?\s+Sleeper\b", re.IGNORECASE), "Deccan Royal sleeper"),
    (re.compile(r"\bGaruda\s+Plus(?:\s+Volvo)?(?:\s+B11R)?\b", re.IGNORECASE), "Garuda Plus"),
    (re.compile(r"\bGreenline(?:\s+Electric)?(?:\s+AC)?\s+Sleeper\b", re.IGNORECASE), "Greenline sleeper"),
    (re.compile(r"\bJabbar(?:\s+Luxury)?(?:\s+AC)?\s+Sleeper\b", re.IGNORECASE), "Jabbar sleeper"),
    (re.compile(r"\bIntrCity(?:\s+Daytime)?(?:\s+Executive)?\b", re.IGNORECASE), "IntrCity"),
    (re.compile(r"\bCyberliner(?:\s+Semi-?Sleeper)?\b", re.IGNORECASE), "Cyberliner semi-sleeper"),
]


def shorten_bus_name_for_voice(name: str) -> str:
    """
    Shortens verbose official bus names into natural spoken names for phone conversations.
    Preserves brand/operator identity and sleeper/seater distinction when helpful,
    while removing chassis, engine, and marketing jargon.

    Examples:
    - 'Kaveri Twilight AC Sleeper' -> 'Kaveri sleeper'
    - 'Krishnaveni Morning Superfast' -> 'Krishnaveni'
    - 'Zingbus Volvo 9600 Multi-Axle Sleeper' -> 'Zingbus sleeper'
    - 'Snehith Express AC Seater' -> 'Snehith Express'
    """
    if not name:
        return ""

    res = name.strip()
    for pattern, replacement in KNOWN_BUS_NAME_REPLACEMENTS:
        if pattern.fullmatch(res):
            return replacement

    is_semi = bool(re.search(r"\bsemi-?sleeper\b", res, re.IGNORECASE))
    is_sleeper = bool(re.search(r"\bsleeper\b", res, re.IGNORECASE))
    is_seater = bool(re.search(r"\bseater\b", res, re.IGNORECASE))

    # Strip marketing and chassis clutter
    cleaned = re.sub(
        r"\b(Volvo(?:\s+9600|\s+B11R)?|Scania|BharatBenz|Multi-?Axle|I-?Shift|Twilight|Morning\s+Superfast|Superfast|Executive|Luxury|Daytime|Electric|AC|Non-AC)\b",
        "",
        res,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    tokens = cleaned.split()
    if not tokens:
        return name

    if len(tokens) >= 2 and tokens[1].lower() in ["express", "travels", "lines", "tours"] and tokens[1].lower() != "express":
        brand = tokens[0]
    elif len(tokens) >= 2 and tokens[1].lower() == "express":
        brand = f"{tokens[0]} Express"
    else:
        brand = tokens[0]

    if is_semi:
        return f"{brand} semi-sleeper"
    elif is_sleeper:
        return f"{brand} sleeper"
    elif is_seater and not brand.endswith("Express"):
        return f"{brand} seater"
    return brand


def shorten_spoken_bus_names_in_text(text: str) -> str:
    """
    Scans conversational text for verbose official bus names and replaces them
    with short, natural spoken names suitable for a voice phone call.
    """
    if not text:
        return ""
    out = text
    for pattern, replacement in KNOWN_BUS_NAME_REPLACEMENTS:
        out = pattern.sub(replacement, out)
    return out


def clean_text_for_tts(text: str, announced_progress_stages: Optional[set] = None) -> str:
    """
    Complete text normalization pipeline for voice TTS playback strictly ordered as:
    1. Agent response -> internal/reasoning stripping.
    2. Instruction narration leak stripping (e.g. 'Thus ask: "..."').
    3. Removal of internal database/bus IDs (e.g. '(bus 2)', 'booking ID 47').
    4. Stripping of arrival/departure times from boarding/dropping points.
    5. Multilingual foreign-script contamination sanitization.
    6. Removal of redundant progress message prefixes if already announced.
    7. Voice conciseness enforcement (~3-7s conversational target, max 25 words).
    8. Bus-name shortening for phone speech.
    9. Markdown stripping (code blocks, bold, italics, bullets, links).
    10. Currency normalization (₹899 -> 899 rupees).
    11. Spoken 12-hour time formatting (21:00 -> 9 PM, 7:15 -> 7:15 AM).
    12. Duplicate AM/PM cleanup (7:15 AM AM -> 7:15 AM).
    13. Final whitespace normalization.
    """
    from voice.time_formatter import format_spoken_times, cleanup_duplicate_ampm

    if not text:
        return ""

    # 1. Strip instruction narration leak (e.g. 'Thus ask: "..."')
    text = strip_instruction_leak(text)
    if not text:
        return ""

    # 2. Strip reasoning tags and internal narration
    text = sanitize_agent_text(text)
    if not text:
        return ""

    # 3. Strip internal database / bus IDs
    text = remove_internal_ids_from_voice(text)
    if not text:
        return ""

    # 4. Strip times from boarding/dropping points
    text = strip_times_from_boarding_points(text)
    if not text:
        return ""

    # 5. Strip foreign script contamination (e.g. CJK)
    text = sanitize_multilingual_contamination(text)
    if not text:
        return ""

    # 6. Strip redundant progress prefixes if progress TTS was already played
    if announced_progress_stages:
        from voice.progress import strip_redundant_progress_prefix
        text = strip_redundant_progress_prefix(text, announced_progress_stages)
        if not text:
            return ""

    # 7. Enforce voice conciseness (~3-8s)
    text = enforce_concise_voice_response(text)
    if not text:
        return ""

    # 8. Shorten verbose bus names for natural phone speech
    text = shorten_spoken_bus_names_in_text(text)

    # 9. Remove markdown code blocks and inline code
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove markdown links: [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Remove raw URLs
    text = re.sub(r"https?://\S+", "", text)

    # Remove markdown formatting (bold, italics, headers, bullets)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*•]\s*", "", text, flags=re.MULTILINE)

    # 10. Currency normalization: ₹899 -> 899 rupees
    text = re.sub(r"\u20b9\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)", r"\1 rupees", text)
    text = text.replace("\u20b9", " rupees ")

    # 11. Format 24-hour departure/arrival times to natural 12-hour spoken format
    text = format_spoken_times(text)

    # 12. Duplicate AM/PM cleanup
    text = cleanup_duplicate_ampm(text)

    # 13. Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_agent_response(agent_result: Any) -> str:
    """
    Extracts purely user-facing text from a Strands AgentResult or similar agent output.
    Explicitly filters out:
    - reasoningContent blocks
    - toolUse / toolResult blocks
    - internal tags (<reasoning>, <thought>, <analysis>, <tool>, etc.)
    - internal narration sentences
    - instruction leaks
    - database IDs
    """
    if agent_result is None:
        return ""

    raw_text = ""

    message = getattr(agent_result, "message", None)
    if isinstance(message, dict):
        content = message.get("content", [])
        if isinstance(content, list):
            text_blocks = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if "reasoningContent" in item or "toolUse" in item or "toolResult" in item:
                    continue
                if "text" in item and isinstance(item["text"], str):
                    text_blocks.append(item["text"])
                elif "citationsContent" in item and isinstance(item["citationsContent"], dict):
                    c_content = item["citationsContent"].get("content", [])
                    for sub in c_content:
                        if isinstance(sub, dict) and "text" in sub:
                            text_blocks.append(sub["text"])
            if text_blocks:
                raw_text = "\n".join(text_blocks)

    if not raw_text:
        structured = getattr(agent_result, "structured_output", None)
        if structured:
            if hasattr(structured, "model_dump_json"):
                raw_text = structured.model_dump_json()
            else:
                raw_text = str(structured)

    if not raw_text:
        raw_text = str(agent_result) if agent_result else ""

    # Primary pipeline: strip instruction leaks, reasoning tags, database IDs, boarding times, foreign scripts
    clean_text = strip_instruction_leak(raw_text)
    clean_text = sanitize_agent_text(clean_text)
    clean_text = remove_internal_ids_from_voice(clean_text)
    clean_text = strip_times_from_boarding_points(clean_text)
    clean_text = sanitize_multilingual_contamination(clean_text)
    clean_text = enforce_concise_voice_response(clean_text)

    return clean_text.strip()
