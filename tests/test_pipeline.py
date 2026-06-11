from unittest.mock import AsyncMock, patch

from bot.models import ClaimResult


async def test_pipeline_no_claims():
    with patch("bot.pipeline.extract_claims", AsyncMock(return_value=[])):
        from bot.pipeline import run_check

        report, results = await run_check("testo senza fatti")
    assert results == [] and "Nessun claim" in report


async def test_pipeline_full_flow():
    cr = ClaimResult(claim="A", verdict="true", confidence="high", sources=["https://a.it"], reasoning="")
    with patch("bot.pipeline.extract_claims", AsyncMock(return_value=["A"])), patch(
        "bot.pipeline.gather_evidence", AsyncMock(return_value=["fake-ev"])
    ), patch("bot.pipeline.judge_claim", AsyncMock(return_value=cr)):
        from bot.pipeline import run_check

        report, results = await run_check("testo", title="T")
    assert len(results) == 1 and "✅" in report
