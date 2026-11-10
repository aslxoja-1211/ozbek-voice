"""Unit tests for the Text Diff Engine and Uzbek apostrophe normalization."""

from app.editor.diff_engine import apply_edit_command
from app.models.schemas import EditorEditCommand


def test_append_smart_spacing_and_punctuation():
    res1 = apply_edit_command(
        "",
        EditorEditCommand(action="APPEND", target="", replacement="Salom dunyo"),
    )
    assert res1.new_text == "Salom dunyo"
    assert res1.changed is True

    res2 = apply_edit_command(
        "Salom dunyo",
        EditorEditCommand(action="APPEND", target="", replacement="bugun havo yaxshi."),
    )
    assert res2.new_text == "Salom dunyo bugun havo yaxshi."

    res3 = apply_edit_command(
        "Salom dunyo",
        EditorEditCommand(action="APPEND", target="", replacement=","),
    )
    assert res3.new_text == "Salom dunyo,"


def test_replace_uzbek_apostrophe_variants():
    # Editor text uses U+2018 (‘), command target uses ASCII (')
    text = "Bugun o‘quvchilar kecha o‘qigan kitobni ko‘rdi."
    cmd = EditorEditCommand(
        action="REPLACE",
        target="o'quvchilar",
        replacement="talabalar",
    )
    res = apply_edit_command(text, cmd)
    assert res.changed is True
    assert res.applied_strategy == "normalized_replace"
    assert res.new_text == "Bugun talabalar kecha o‘qigan kitobni ko‘rdi."
    assert res.matched_span is not None
    assert res.matched_span.matched_text == "o‘quvchilar"


def test_replace_prefers_last_occurrence():
    text = "Kecha keldim, kecha ketdim."
    cmd = EditorEditCommand(action="REPLACE", target="kecha", replacement="bugun")
    res = apply_edit_command(text, cmd)
    assert res.new_text == "Kecha keldim, bugun ketdim."


def test_delete_tidies_spaces_and_supports_clear_all():
    res = apply_edit_command(
        "Men kecha ofisga bordim.",
        EditorEditCommand(action="DELETE", target="kecha", replacement=""),
    )
    assert res.changed is True
    assert res.new_text == "Men ofisga bordim."

    cleared = apply_edit_command(
        "Har qanday matn.",
        EditorEditCommand(action="DELETE", target="*", replacement=""),
    )
    assert cleared.new_text == ""
    assert cleared.applied_strategy == "clear_all"


def test_format_and_updated_full_text_fallback():
    fmt = apply_edit_command(
        "Birinchi, ikkinchi",
        EditorEditCommand(
            action="FORMAT",
            target="Birinchi, ikkinchi",
            replacement="- Birinchi\n- ikkinchi",
        ),
    )
    assert fmt.changed is True
    assert fmt.format_hint == "bullet_list"
    assert fmt.new_text == "- Birinchi\n- ikkinchi"

    fallback = apply_edit_command(
        "Murakkab matn.",
        EditorEditCommand(
            action="REPLACE",
            target="yo'q so'z",
            replacement="boshqa",
            updated_full_text="Yangilangan to'liq matn.",
        ),
    )
    assert fallback.applied_strategy == "full_text_fallback"
    assert fallback.new_text == "Yangilangan to'liq matn."
