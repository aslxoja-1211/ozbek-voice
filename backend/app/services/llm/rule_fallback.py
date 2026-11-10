"""Deterministic Uzbek rule-based Intent Engine for demo mode and fallback."""

import re

from app.editor.uzbek_text import (
    capitalize_first_alpha,
    extract_last_sentence,
    extract_last_word,
    find_target_span,
    normalize_uzbek_apostrophes,
)
from app.models.schemas import EditorEditCommand
from app.services.llm.base import IntentEngine, IntentResult

REPLACE_PATTERNS = (
    re.compile(
        r"^(.+?)\s+so'zini\s+(.+?)\s+(?:deb\s+o'zgartir|ga\s+o'zgartir|ga\s+almashtir|bilan\s+almashtir|deb\s+yoz)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(.+?)\s+o'rniga\s+(.+?)\s+(?:yoz|qo'y|deb\s+o'zgartir|deb\s+almashtir)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(.+?)(?:\s+ni|ni)\s+(.+?)(?:\s+deb\s+o'zgartir|ga\s+o'zgartir|ga\s+almashtir|\s+bilan\s+almashtir|\s+deb\s+yoz)$",
        re.IGNORECASE,
    ),
)

DELETE_NAMED_PATTERNS = (
    re.compile(
        r"^(.+?)\s+(?:so'zini|gapini|jumlasini|qismini)\s+(?:o'chir|olib\s+tashla|o'chirib\s+tashla)$"
    ),
    re.compile(r"^(.+?)\s+ni\s+(?:o'chir|olib\s+tashla|o'chirib\s+tashla)$"),
    re.compile(r"^(.+?)ni\s+(?:o'chir|olib\s+tashla|o'chirib\s+tashla)$"),
)

PUNCTUATION_COMMANDS = {
    "nuqta qo'y": ".",
    "vergul qo'y": ",",
    "undov qo'y": "!",
    "undov belgisi qo'y": "!",
    "so'roq qo'y": "?",
    "so'roq belgisi qo'y": "?",
    "ikki nuqta qo'y": ":",
}


def _strip_quotes(text: str) -> str:
    return text.strip().strip("\"'«»“”‘’`")


def _clean_command_transcript(raw: str) -> tuple[str, str, str]:
    """Return (trimmed_original, apostrophe_norm_cased, normalized_lowercase)."""
    trimmed = raw.strip()
    cased = re.sub(r"[.!?]+$", "", normalize_uzbek_apostrophes(trimmed)).strip()
    norm = cased.lower()
    return trimmed, cased, norm


def _should_capitalize_append(current_state: str) -> bool:
    stripped = current_state.rstrip()
    if not stripped:
        return True
    return stripped[-1] in {".", "!", "?", "\n"}


def _to_bullet_list(segment: str) -> str:
    """Convert a phrase or comma-separated items into Markdown bullet lines."""
    if not segment:
        return "- "
    parts = [p.strip() for p in re.split(r"\s*[,;]\s*", segment) if p.strip()]
    if len(parts) > 1:
        return "\n".join(f"- {part.lstrip('- ')}" for part in parts)
    return f"- {segment.lstrip('- ')}"


class RuleFallbackIntentEngine(IntentEngine):
    """Fast local heuristic parser for Uzbek dictation and voice edit commands."""

    name = "mock"
    is_mock = True

    async def resolve_intent(
        self,
        current_editor_state: str,
        raw_transcript: str,
    ) -> IntentResult:
        """Resolve Uzbek intent locally without external API calls."""
        cmd = self._parse(current_editor_state, raw_transcript)
        return IntentResult(
            command=cmd,
            provider=self.name,
            is_mock=True,
            note="Demo/Lokal Intent Engine faol (Gemini yoki OpenAI kaliti kiritilmagan).",
        )

    def _parse(self, state: str, raw_transcript: str) -> EditorEditCommand:
        trimmed, cased, norm = _clean_command_transcript(raw_transcript)
        if not trimmed:
            return EditorEditCommand(
                action="APPEND",
                target="",
                replacement="",
                updated_full_text=None,
                confidence=0.0,
            )

        # 1. DELETE commands
        if norm in {
            "hammasini o'chir",
            "barchasini o'chir",
            "hamma matnni o'chir",
            "matnni tozala",
            "tozala",
        }:
            return EditorEditCommand(
                action="DELETE",
                target="*",
                replacement="",
                confidence=0.99,
            )

        if norm in {
            "oxirgi gapni o'chir",
            "so'nggi gapni o'chir",
            "oxirgi jumlani o'chir",
            "oxirgi gapni olib tashla",
        }:
            last_sent = extract_last_sentence(state)
            return EditorEditCommand(
                action="DELETE",
                target=last_sent,
                replacement="",
                confidence=0.96 if last_sent else 0.6,
            )

        if norm in {
            "oxirgi so'zni o'chir",
            "so'nggi so'zni o'chir",
            "oxirgi so'zni olib tashla",
        }:
            last_word = extract_last_word(state)
            return EditorEditCommand(
                action="DELETE",
                target=last_word,
                replacement="",
                confidence=0.96 if last_word else 0.6,
            )

        for pattern in DELETE_NAMED_PATTERNS:
            match = pattern.match(norm)
            if match:
                candidate = _strip_quotes(match.group(1))
                span = find_target_span(state, candidate)
                return EditorEditCommand(
                    action="DELETE",
                    target=span.matched_text if span else candidate,
                    replacement="",
                    confidence=0.93 if span else 0.72,
                )

        # 2. REPLACE commands (matched against case-preserving normalized text)
        for pattern in REPLACE_PATTERNS:
            match = pattern.match(cased)
            if match:
                raw_target = _strip_quotes(match.group(1))
                raw_repl = _strip_quotes(match.group(2))
                span = find_target_span(state, raw_target)
                return EditorEditCommand(
                    action="REPLACE",
                    target=span.matched_text if span else raw_target,
                    replacement=raw_repl,
                    confidence=0.95 if span else 0.78,
                )

        # 3. FORMAT commands
        if norm in PUNCTUATION_COMMANDS:
            return EditorEditCommand(
                action="FORMAT",
                target="",
                replacement=PUNCTUATION_COMMANDS[norm],
                confidence=0.97,
            )

        if norm in {"yangi xatboshi", "xatboshi qo'sh", "yangi abzas"}:
            return EditorEditCommand(
                action="FORMAT",
                target="",
                replacement="\n\n",
                confidence=0.97,
            )

        if norm in {"yangi qator", "keyingi qator", "keyingi qatorga tush"}:
            return EditorEditCommand(
                action="FORMAT",
                target="",
                replacement="\n",
                confidence=0.97,
            )

        if norm in {
            "oxirgi gapni ro'yxatga aylantir",
            "ro'yxatga aylantir",
            "ro'yxat qil",
            "ro'yxat ko'rinishida yoz",
        }:
            last_sent = extract_last_sentence(state)
            if last_sent:
                return EditorEditCommand(
                    action="FORMAT",
                    target=last_sent,
                    replacement=_to_bullet_list(last_sent),
                    confidence=0.93,
                )
            return EditorEditCommand(
                action="FORMAT",
                target="",
                replacement="- ",
                confidence=0.85,
            )

        if norm in {
            "bosh harf bilan yoz",
            "oxirgi gapni bosh harf bilan yoz",
            "katta harfga o'zgartir",
        }:
            last_sent = extract_last_sentence(state)
            if last_sent:
                return EditorEditCommand(
                    action="FORMAT",
                    target=last_sent,
                    replacement=capitalize_first_alpha(last_sent),
                    confidence=0.94,
                )

        if norm in {"sarlavha qil", "oxirgi gapni sarlavha qil"}:
            last_sent = extract_last_sentence(state)
            if last_sent:
                clean_title = last_sent.lstrip("# ").rstrip(".")
                return EditorEditCommand(
                    action="FORMAT",
                    target=last_sent,
                    replacement=f"# {clean_title}",
                    confidence=0.92,
                )

        if norm in {"qalin qil", "oxirgi gapni qalin qil", "oxirgi so'zni qalin qil"}:
            target = (
                extract_last_word(state)
                if "so'zni" in norm
                else extract_last_sentence(state)
            )
            if target:
                return EditorEditCommand(
                    action="FORMAT",
                    target=target,
                    replacement=f"**{target.strip('*')}**",
                    confidence=0.91,
                )

        # 4. Default APPEND dictation
        addition = (
            capitalize_first_alpha(trimmed)
            if _should_capitalize_append(state)
            else trimmed
        )
        return EditorEditCommand(
            action="APPEND",
            target="",
            replacement=addition,
            updated_full_text=None,
            confidence=0.92,
        )
