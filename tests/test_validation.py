from bot.models import Evidence, EvidenceQuote, JudgeOutput
from bot.validation import compute_confidence, validate_judge_output

EVIDENCES = [
    Evidence(
        url="https://www.istat.it/x",
        content="Il PIL è cresciuto del 2% nel 2025.",
        tier=1,
    ),
    Evidence(url="https://ansa.it/y", content="PIL su del 2 per cento secondo Istat.", tier=1),
]


def _judge(verdict="true", quotes=None):
    return JudgeOutput(verdict=verdict, evidence_used=quotes or [], reasoning="r")


def test_url_inventato_declassa():
    j = _judge(quotes=[EvidenceQuote(url="https://inventato.example/z", quote="Il PIL è cresciuto")])
    result = validate_judge_output(j, EVIDENCES)
    assert result.verdict == "unverifiable"


def test_quote_inventata_declassa():
    j = _judge(quotes=[EvidenceQuote(url="https://www.istat.it/x", quote="frase mai scritta")])
    result = validate_judge_output(j, EVIDENCES)
    assert result.verdict == "unverifiable"


def test_quote_valida_normalizzata():
    j = _judge(quotes=[EvidenceQuote(url="https://www.istat.it/x", quote="il pil È cresciuto del 2%")])
    result = validate_judge_output(j, EVIDENCES)
    assert result.verdict == "true"
    assert result.valid_quotes[0].url == "https://www.istat.it/x"


def test_quote_fuzzy_parola_mancante_accettata():
    # quote lunga con una parola saltata: 85%+ contiguo presente → valida
    j = _judge(quotes=[EvidenceQuote(url="https://www.istat.it/x", quote="Il PIL è cresciuto del 2% nel 2025.")])
    evs = [Evidence(url="https://www.istat.it/x",
                    content="Secondo i dati, il PIL è cresciuto del 2% nel 2025, confermando il trend.",
                    tier=1)]
    assert validate_judge_output(j, evs).verdict == "true"


def test_quote_fuzzy_corta_richiede_esatto():
    j = _judge(quotes=[EvidenceQuote(url="https://www.istat.it/x", quote="PIL giù 5%")])
    assert validate_judge_output(j, EVIDENCES).verdict == "unverifiable"


def test_verdetto_senza_evidenze_forzato_unverifiable():
    j = _judge(verdict="false", quotes=[])
    assert validate_judge_output(j, EVIDENCES).verdict == "unverifiable"


def test_confidence_due_tier1_concordi_high():
    assert compute_confidence("true", [EVIDENCES[0], EVIDENCES[1]]) == "high"


def test_confidence_una_fonte_low():
    assert compute_confidence("true", [EVIDENCES[0]]) == "low"


def test_confidence_unverifiable_sempre_low():
    assert compute_confidence("unverifiable", EVIDENCES) == "low"
