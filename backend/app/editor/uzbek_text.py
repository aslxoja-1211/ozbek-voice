"""Shared Uzbek text normalization, sentence splitting, and span matching helpers."""

import re
from typing import Literal, Optional

from app.models.schemas import TextSpan

APOSTROPHE_VARIANTS = frozenset({"'", "‘", "’", "ʻ", "ʼ", "`", "´"})
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

UNDO_VOICE_COMMANDS = frozenset(
    {
        "bekor qil",
        "oxirgi amalni bekor qil",
        "tahrirni bekor qil",
        "orqaga qaytar",
        "oldingi holatga qaytar",
        "undo",
    }
)

REDO_VOICE_COMMANDS = frozenset(
    {
        "oldinga qaytar",
        "qayta tikla",
        "bekor qilinganni qaytar",
        "redo",
    }
)


def detect_client_action(transcript: str) -> Optional[Literal["UNDO", "REDO"]]:
    """Return 'UNDO' or 'REDO' when transcript is an exact voice history command."""
    norm = normalize_uzbek_apostrophes(transcript.strip()).lower()
    norm = re.sub(r"[.!?]+$", "", norm).strip()
    if norm in UNDO_VOICE_COMMANDS:
        return "UNDO"
    if norm in REDO_VOICE_COMMANDS:
        return "REDO"
    return None


def normalize_uzbek_apostrophes(text: str) -> str:
    """Canonicalize Uzbek Latin apostrophe variants to ASCII single quote."""
    if not text:
        return ""
    return "".join("'" if ch in APOSTROPHE_VARIANTS else ch for ch in text)


def canonicalize_for_match(text: str) -> str:
    """Normalize apostrophes and lowercase text while preserving 1-to-1 character indices."""
    return normalize_uzbek_apostrophes(text).lower()


def find_target_span(
    haystack: str,
    needle: str,
    prefer_last: bool = True,
) -> Optional[TextSpan]:
    """Locate `needle` inside `haystack`, tolerating Uzbek apostrophe and case differences."""
    if not haystack or not needle:
        return None

    clean_needle = needle.strip()
    if not clean_needle:
        return None

    search_fn = str.rfind if prefer_last else str.find

    # 1. Exact substring match
    idx = search_fn(haystack, clean_needle)
    if idx != -1:
        end = idx + len(clean_needle)
        return TextSpan(start=idx, end=end, matched_text=haystack[idx:end])

    # 2. Apostrophe-canonical match (1-to-1 length preserved)
    norm_haystack = normalize_uzbek_apostrophes(haystack)
    norm_needle = normalize_uzbek_apostrophes(clean_needle)
    idx = search_fn(norm_haystack, norm_needle)
    if idx != -1:
        end = idx + len(norm_needle)
        return TextSpan(start=idx, end=end, matched_text=haystack[idx:end])

    # 3. Case-insensitive + apostrophe-canonical match (1-to-1 length preserved)
    canon_haystack = norm_haystack.lower()
    canon_needle = norm_needle.lower()
    if len(canon_haystack) == len(haystack):
        idx = search_fn(canon_haystack, canon_needle)
        if idx != -1:
            end = idx + len(canon_needle)
            return TextSpan(start=idx, end=end, matched_text=haystack[idx:end])

    # 4. Flexible whitespace regex over normalized text
    tokens = [re.escape(tok) for tok in canon_needle.split()]
    if tokens:
        pattern = re.compile(r"\s+".join(tokens))
        matches = list(pattern.finditer(canon_haystack))
        if matches:
            chosen = matches[-1] if prefer_last else matches[0]
            return TextSpan(
                start=chosen.start(),
                end=chosen.end(),
                matched_text=haystack[chosen.start() : chosen.end()],
            )

    return None


def extract_last_sentence(text: str) -> str:
    """Return the last non-empty sentence or line from `text`."""
    stripped = text.strip()
    if not stripped:
        return ""
    parts = [p.strip() for p in SENTENCE_SPLIT_RE.split(stripped) if p.strip()]
    return parts[-1] if parts else stripped


def extract_last_word(text: str) -> str:
    """Return the last whitespace-delimited token from `text`."""
    tokens = text.strip().split()
    return tokens[-1] if tokens else ""


def capitalize_first_alpha(text: str) -> str:
    """Capitalize the first alphabetic character in `text`, leaving leading whitespace intact."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1 :]
    return text
