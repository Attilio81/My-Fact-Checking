from unittest.mock import AsyncMock, patch

from bot.models import Evidence, EvidenceQuote, JudgeOutput

EVS = [Evidence(url="https://istat.it/a", content="Il PIL è cresciuto del 2%.", tier=1)]


async def test_judge_returns_validated_result():
    fake = JudgeOutput(
        verdict="true",
        evidence_used=[EvidenceQuote(url="https://istat.it/a", quote="Il PIL è cresciuto del 2%")],
        reasoning="confermato",
    )
    with patch("bot.agents.judge._get_agent") as ga:
        ga.return_value.arun = AsyncMock(return_value=type("R", (), {"content": fake})())
        from bot.agents.judge import judge_claim

        result = await judge_claim("Il PIL è cresciuto del 2%", EVS)
    assert result.verdict == "true"
    assert result.confidence in ("high", "medium", "low")
    assert result.sources == ["https://istat.it/a"]


async def test_judge_no_evidence_short_circuit():
    from bot.agents.judge import judge_claim

    result = await judge_claim("claim", [])
    assert result.verdict == "unverifiable"


async def test_judge_failure_unverifiable():
    with patch("bot.agents.judge._get_agent") as ga:
        ga.return_value.arun = AsyncMock(side_effect=RuntimeError("down"))
        from bot.agents.judge import judge_claim

        result = await judge_claim("claim", EVS)
    assert result.verdict == "unverifiable"
