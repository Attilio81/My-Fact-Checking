from unittest.mock import AsyncMock, patch

from bot.models import ExtractedClaims


async def test_extract_claims_returns_list():
    fake = ExtractedClaims(claims=["Il PIL è cresciuto del 2% nel 2025"])
    with patch("bot.agents.extractor._get_agent") as ga:
        ga.return_value.arun = AsyncMock(return_value=type("R", (), {"content": fake})())
        from bot.agents.extractor import extract_claims

        claims = await extract_claims("testo articolo lungo...")
    assert claims == ["Il PIL è cresciuto del 2% nel 2025"]


async def test_extract_claims_failure_returns_empty():
    with patch("bot.agents.extractor._get_agent") as ga:
        ga.return_value.arun = AsyncMock(side_effect=RuntimeError("api down"))
        from bot.agents.extractor import extract_claims

        assert await extract_claims("testo") == []
