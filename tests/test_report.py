from bot.models import ClaimResult
from bot.report import format_report


def test_format_report_per_claim():
    results = [
        ClaimResult(claim="A", verdict="true", confidence="high", sources=["https://a.it/x"], reasoning="ok"),
        ClaimResult(claim="B", verdict="false", confidence="medium", sources=["https://b.it/y"], reasoning="no"),
        ClaimResult(claim="C", verdict="unverifiable", confidence="low", sources=[], reasoning=""),
    ]
    report = format_report("Titolo notizia", results)
    assert "✅" in report and "❌" in report and "⚠️" in report
    assert "Titolo notizia" in report
    assert "https://a.it/x" in report


def test_overall_mostly_true_no_false():
    results = [
        ClaimResult(claim=c, verdict="true", confidence="high", sources=["https://x.it"], reasoning="")
        for c in "ABCD"
    ] + [ClaimResult(claim="E", verdict="unverifiable", confidence="low", sources=[], reasoning="")]
    report = format_report("T", results)
    assert "sostanzialmente confermata" in report
    assert "4 claim su 5" in report


def test_overall_judgment_mostly_false():
    results = [
        ClaimResult(claim=c, verdict="false", confidence="high", sources=["https://x.it"], reasoning="")
        for c in "AB"
    ]
    assert "non attendibile" in format_report("T", results).lower()
