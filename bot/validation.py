import re
import unicodedata
from dataclasses import dataclass, field

from bot.models import Confidence, Evidence, EvidenceQuote, JudgeOutput, Verdict


@dataclass
class ValidatedVerdict:
    verdict: Verdict
    valid_quotes: list[EvidenceQuote] = field(default_factory=list)
    valid_evidences: list[Evidence] = field(default_factory=list)
    reasoning: str = ""


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%]", "", text)).strip()


def validate_judge_output(judge: JudgeOutput, evidences: list[Evidence]) -> ValidatedVerdict:
    """Validazione meccanica: URL citati devono esistere tra le evidenze recuperate,
    le quote devono comparire nel testo dell'evidenza. Violazione → unverifiable."""
    by_url = {e.url: e for e in evidences}
    valid_quotes: list[EvidenceQuote] = []
    valid_evidences: list[Evidence] = []
    for q in judge.evidence_used:
        ev = by_url.get(q.url)
        if ev is None:
            continue  # URL inventato
        if _normalize(q.quote) not in _normalize(ev.content):
            continue  # citazione inventata
        valid_quotes.append(q)
        if ev not in valid_evidences:
            valid_evidences.append(ev)

    verdict = judge.verdict
    if verdict in ("true", "false") and not valid_quotes:
        verdict = "unverifiable"
    return ValidatedVerdict(
        verdict=verdict,
        valid_quotes=valid_quotes,
        valid_evidences=valid_evidences,
        reasoning=judge.reasoning,
    )


def compute_confidence(verdict: Verdict, valid_evidences: list[Evidence]) -> Confidence:
    """Confidenza calcolata in codice, non autodichiarata dal modello."""
    if verdict == "unverifiable":
        return "low"
    domains = {e.url.split("/")[2] for e in valid_evidences if "//" in e.url}
    strong = [e for e in valid_evidences if e.tier <= 1]
    if len(strong) >= 2 and len(domains) >= 2:
        return "high"
    if len(valid_evidences) >= 2 and len(domains) >= 2:
        return "medium"
    return "low"
