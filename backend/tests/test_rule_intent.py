"""Tests for Uzbek deterministic rule-based Intent Engine."""

import pytest

from app.services.llm.rule_fallback import RuleFallbackIntentEngine


@pytest.mark.asyncio
async def test_rule_intent_append_and_capitalization():
    engine = RuleFallbackIntentEngine()
    res = await engine.resolve_intent("", "bugun yangi loyiha boshlandi.")
    assert res.command.action == "APPEND"
    assert res.command.replacement == "Bugun yangi loyiha boshlandi."

    res_mid = await engine.resolve_intent("Bugun", "juda yaxshi kun")
    assert res_mid.command.action == "APPEND"
    assert res_mid.command.replacement == "juda yaxshi kun"


@pytest.mark.asyncio
async def test_rule_intent_replace_uzbek_commands():
    engine = RuleFallbackIntentEngine()
    res1 = await engine.resolve_intent(
        "Men kecha Toshkentda edim.",
        "kecha so‘zini bugun deb o‘zgartir",
    )
    assert res1.command.action == "REPLACE"
    assert res1.command.target == "kecha"
    assert res1.command.replacement == "bugun"

    res2 = await engine.resolve_intent(
        "Men Toshkentda edim.",
        "Toshkentni Samarqandga almashtir",
    )
    assert res2.command.action == "REPLACE"
    assert res2.command.target == "Toshkent"
    assert res2.command.replacement == "Samarqand"


@pytest.mark.asyncio
async def test_rule_intent_delete_commands():
    engine = RuleFallbackIntentEngine()

    last_sent = await engine.resolve_intent(
        "Birinchi gap. Ikkinchi gap.",
        "oxirgi gapni o'chir",
    )
    assert last_sent.command.action == "DELETE"
    assert last_sent.command.target == "Ikkinchi gap."

    last_word = await engine.resolve_intent("Salom dunyo", "oxirgi so'zni o'chir")
    assert last_word.command.action == "DELETE"
    assert last_word.command.target == "dunyo"

    clear_all = await engine.resolve_intent("Nimadir", "hammasini o'chir")
    assert clear_all.command.action == "DELETE"
    assert clear_all.command.target == "*"


@pytest.mark.asyncio
async def test_rule_intent_format_commands():
    engine = RuleFallbackIntentEngine()

    bullet = await engine.resolve_intent(
        "Reja: tahlil, kodlash, test",
        "oxirgi gapni ro'yxatga aylantir",
    )
    assert bullet.command.action == "FORMAT"
    assert "- " in bullet.command.replacement

    para = await engine.resolve_intent("Matn.", "yangi xatboshi")
    assert para.command.action == "FORMAT"
    assert para.command.replacement == "\n\n"

    heading = await engine.resolve_intent("Kirish.", "sarlavha qil")
    assert heading.command.action == "FORMAT"
    assert heading.command.replacement == "# Kirish"
