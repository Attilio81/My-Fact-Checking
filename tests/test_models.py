from bot.models import ClaimResult, EvidenceQuote, JudgeOutput


def test_judge_output_verdict_enum():
    j = JudgeOutput(
        verdict="true",
        evidence_used=[EvidenceQuote(url="https://a.it", quote="x")],
        reasoning="r",
    )
    assert j.verdict == "true"


def test_claim_result_defaults():
    r = ClaimResult(
        claim="c", verdict="unverifiable", confidence="low", sources=[], reasoning=""
    )
    assert r.sources == []
