import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

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


_FUZZY_MIN_LEN = 20  # sotto questa lunghezza solo match esatto
_FUZZY_RATIO = 0.85  # frazione contigua della quote che deve esistere nel testo


def _quote_in_text(quote_norm: str, content_norm: str) -> bool:
    """Match esatto, oppure fuzzy: almeno l'85% contiguo della quote presente
    nel testo (tollera una parola saltata o punteggiatura diversa, non frasi
    inventate)."""
    if quote_norm in content_norm:
        return True
    if len(quote_norm) < _FUZZY_MIN_LEN:
        return False
    m = SequenceMatcher(None, quote_norm, content_norm, autojunk=False).find_longest_match(
        0, len(quote_norm), 0, len(content_norm)
    )
    return m.size / len(quote_norm) >= _FUZZY_RATIO


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
        if not _quote_in_text(_normalize(q.quote), _normalize(ev.content)):
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
