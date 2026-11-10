"""Text Diff Engine applying strict EditorEditCommand payloads safely."""

import re

from app.editor.uzbek_text import find_target_span
from app.models.schemas import ApplyResult, EditorEditCommand

LEADING_PUNCTUATION = frozenset({".", ",", "!", "?", ";", ":", ")", "]", "»", "”"})


def _smart_append(current_text: str, addition: str) -> str:
    """Join `addition` onto `current_text` with natural spacing."""
    if not addition:
        return current_text
    if not current_text:
        return addition.lstrip(" ")

    # Explicit leading newline or punctuation shouldn't receive an extra space.
    if addition.startswith("\n") or addition[0] in LEADING_PUNCTUATION:
        return current_text.rstrip(" ") + addition

    if current_text.endswith((" ", "\n", "\t")):
        return current_text + addition.lstrip(" ")

    return f"{current_text} {addition.lstrip(' ')}"


def _splice_and_tidy(text: str, start: int, end: int, replacement: str) -> str:
    """Splice replacement into [start:end] and normalize awkward leftover whitespace."""
    before = text[:start]
    after = text[end:]

    if replacement:
        return before + replacement + after

    # Deletion tidying: collapse double spaces caused by removing a middle word.
    combined = before + after
    if before.endswith(" ") and after.startswith(" "):
        combined = before[:-1] + after
    elif before.endswith(" ") and after and after[0] in LEADING_PUNCTUATION:
        combined = before[:-1] + after

    combined = re.sub(r"[ \t]{2,}", " ", combined)
    combined = re.sub(r"\n[ \t]+", "\n", combined)
    combined = re.sub(r"\n{3,}", "\n\n", combined)
    return combined.strip(" ")


def _infer_format_hint(cmd: EditorEditCommand) -> str | None:
    """Infer rich-text hint from replacement structure when action is FORMAT."""
    candidate = (cmd.replacement or cmd.updated_full_text or "").strip()
    if not candidate:
        return None
    if candidate.startswith(("- ", "* ")):
        return "bullet_list"
    if candidate.startswith("# "):
        return "heading_1"
    if candidate.startswith("## "):
        return "heading_2"
    if candidate.startswith("**") and candidate.endswith("**"):
        return "bold"
    if "\n\n" in candidate or candidate.startswith("\n"):
        return "paragraph"
    return None


def apply_edit_command(current_text: str, cmd: EditorEditCommand) -> ApplyResult:
    """Apply an EditorEditCommand deterministically to `current_text`."""
    previous = current_text or ""

    if cmd.action == "APPEND":
        if cmd.replacement:
            new_text = _smart_append(previous, cmd.replacement)
            return ApplyResult(
                previous_text=previous,
                new_text=new_text,
                changed=new_text != previous,
                applied_strategy="append",
            )
        if cmd.updated_full_text is not None:
            return ApplyResult(
                previous_text=previous,
                new_text=cmd.updated_full_text,
                changed=cmd.updated_full_text != previous,
                applied_strategy="full_text_fallback",
            )
        return ApplyResult(
            previous_text=previous,
            new_text=previous,
            changed=False,
            applied_strategy="noop",
        )

    if cmd.action == "DELETE":
        if cmd.target.strip() in {"*", "__ALL__"}:
            return ApplyResult(
                previous_text=previous,
                new_text="",
                changed=previous != "",
                applied_strategy="clear_all",
            )

        span = find_target_span(previous, cmd.target)
        if span is not None:
            new_text = _splice_and_tidy(previous, span.start, span.end, "")
            return ApplyResult(
                previous_text=previous,
                new_text=new_text,
                changed=new_text != previous,
                applied_strategy="delete_span",
                matched_span=span,
            )

        if cmd.updated_full_text is not None:
            return ApplyResult(
                previous_text=previous,
                new_text=cmd.updated_full_text,
                changed=cmd.updated_full_text != previous,
                applied_strategy="full_text_fallback",
            )

        return ApplyResult(
            previous_text=previous,
            new_text=previous,
            changed=False,
            applied_strategy="target_not_found",
        )

    # REPLACE and FORMAT share targeted span replacement + full_text fallback.
    format_hint = _infer_format_hint(cmd) if cmd.action == "FORMAT" else None

    if cmd.target:
        span = find_target_span(previous, cmd.target)
        if span is not None:
            new_text = _splice_and_tidy(previous, span.start, span.end, cmd.replacement)
            strategy = (
                "format_span"
                if cmd.action == "FORMAT"
                else (
                    "exact_replace"
                    if span.matched_text == cmd.target.strip()
                    else "normalized_replace"
                )
            )
            return ApplyResult(
                previous_text=previous,
                new_text=new_text,
                changed=new_text != previous,
                applied_strategy=strategy,
                matched_span=span,
                format_hint=format_hint,
            )

    if cmd.updated_full_text is not None:
        return ApplyResult(
            previous_text=previous,
            new_text=cmd.updated_full_text,
            changed=cmd.updated_full_text != previous,
            applied_strategy="full_text_fallback",
            format_hint=format_hint,
        )

    # FORMAT without a target (e.g., "yangi xatboshi" -> append newline/punctuation)
    if cmd.action == "FORMAT" and cmd.replacement:
        new_text = _smart_append(previous, cmd.replacement)
        return ApplyResult(
            previous_text=previous,
            new_text=new_text,
            changed=new_text != previous,
            applied_strategy="format_append",
            format_hint=format_hint,
        )

    return ApplyResult(
        previous_text=previous,
        new_text=previous,
        changed=False,
        applied_strategy="target_not_found",
        format_hint=format_hint,
    )
